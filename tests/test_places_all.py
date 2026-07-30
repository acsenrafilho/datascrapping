"""Tests for places.all pipeline orchestrator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from datascrapping.core.base import ScrapeContext, ScrapeResult
from datascrapping.scrapers.places.all import PlacesAllScraper


def _ctx(tmp_path: Path, **extras) -> ScrapeContext:
    return ScrapeContext(out_dir=tmp_path, extras=extras)


def test_places_all_missing_city():
    scraper = PlacesAllScraper()
    result = scraper.run(_ctx(Path("/tmp"), state="SP"))
    assert result.errors == 1
    assert "city" in (result.message or "").lower()


def test_places_all_dry_run(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    scraper = PlacesAllScraper()
    ctx = _ctx(tmp_path, city="Campinas", state="SP", skip_geo_check=True)
    ctx.dry_run = True
    result = scraper.run(ctx)
    assert result.errors == 0
    assert "places.all" in result.message
    assert "places.search" in result.message
    assert "places.website" in result.message
    assert "places.cnpj" in result.message
    assert "campinas_sp_aasi" in result.message


def test_places_all_runs_three_stages(tmp_path):
    folder = tmp_path / "places" / "campinas_sp_aasi"
    folder.mkdir(parents=True)
    (folder / "places.csv").write_text("place_id\n", encoding="utf-8")
    (folder / "places_enriched.csv").write_text("place_id\n", encoding="utf-8")
    (folder / "places_full.csv").write_text("place_id\n", encoding="utf-8")

    search = MagicMock()
    search.return_value.run.return_value = ScrapeResult(
        scraper="places.search", saved=2, message="ok search"
    )
    website = MagicMock()
    website.return_value.run.return_value = ScrapeResult(
        scraper="places.website", saved=2, message="ok website"
    )
    cnpj = MagicMock()
    cnpj.return_value.run.return_value = ScrapeResult(
        scraper="places.cnpj", saved=1, message="ok cnpj"
    )

    def _get(name: str):
        return {
            "places.search": search,
            "places.website": website,
            "places.cnpj": cnpj,
        }[name]

    scraper = PlacesAllScraper()
    with patch("datascrapping.scrapers.places.all.registry.get", side_effect=_get):
        result = scraper.run(
            _ctx(
                tmp_path,
                city="Campinas",
                state="SP",
                skip_geo_check=True,
                skip_llm=True,
            )
        )

    assert result.errors == 0
    assert result.saved == 5
    assert result.output_path == folder / "places_full.csv"
    assert "ok search" in result.message
    assert "ok website" in result.message
    assert "ok cnpj" in result.message

    # website/cnpj received folder as from_path
    website_ctx = website.return_value.run.call_args[0][0]
    assert website_ctx.extras["from_path"] == str(folder)
    assert website_ctx.extras["skip_llm"] is True
    cnpj_ctx = cnpj.return_value.run.call_args[0][0]
    assert cnpj_ctx.extras["from_path"] == str(folder)


def test_places_all_aborts_without_places_csv(tmp_path):
    search = MagicMock()
    search.return_value.run.return_value = ScrapeResult(
        scraper="places.search",
        errors=1,
        message="failed_geo_check: bad",
    )

    scraper = PlacesAllScraper()
    with patch(
        "datascrapping.scrapers.places.all.registry.get",
        return_value=search,
    ):
        result = scraper.run(
            _ctx(tmp_path, city="X", state="SP", skip_geo_check=True)
        )

    assert result.errors >= 1
    assert "aborted after places.search" in result.message
    assert search.return_value.run.call_count == 1
