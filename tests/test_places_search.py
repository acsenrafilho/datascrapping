import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from datascrapping.core.base import ScrapeContext
from datascrapping.scrapers.places.client import (
    PLACE_DETAILS_QUOTA_COST,
    TEXT_SEARCH_QUOTA_COST,
)
from datascrapping.scrapers.places.search import PlacesSearchScraper

FIXTURES = Path(__file__).parent / "fixtures" / "places"


def _search_fields():
    payload = json.loads((FIXTURES / "text_search_page.json").read_text())
    from datascrapping.scrapers.places.client import place_to_fields

    return [place_to_fields(payload["places"][0])]


def _details_fields():
    payload = json.loads((FIXTURES / "details.json").read_text())
    from datascrapping.scrapers.places.client import place_to_fields

    return place_to_fields(payload)


def test_dry_run_skips_places_http(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    scraper = PlacesSearchScraper()
    ctx = ScrapeContext(
        out_dir=tmp_path,
        dry_run=True,
        extras={
            "city": "Campinas",
            "state": "SP",
            "niche": "aasi",
            "skip_geo_check": True,
        },
    )
    with patch(
        "datascrapping.scrapers.places.search.PlacesClient"
    ) as client_cls:
        result = scraper.run(ctx)
        client_cls.assert_not_called()
    assert result.saved == 0
    assert "dry_run" in result.message
    assert result.output_path is not None
    assert result.output_path.name == "places.csv"


def test_run_saves_one_place(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    scraper = PlacesSearchScraper()
    ctx = ScrapeContext(
        out_dir=tmp_path,
        dry_run=False,
        extras={
            "city": "Campinas",
            "state": "SP",
            "niche": "aasi",
            "skip_geo_check": True,
            "max_quota": 20000,
        },
    )

    mock_client = MagicMock()
    # Only first term returns a place; others empty to keep test fast
    call_count = {"n": 0}

    def search_pages(term, city, state):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [(_search_fields(), TEXT_SEARCH_QUOTA_COST)]
        return [([], TEXT_SEARCH_QUOTA_COST)]

    mock_client.search_text_pages.side_effect = search_pages
    mock_client.get_details.return_value = _details_fields()

    with patch(
        "datascrapping.scrapers.places.search.PlacesClient",
        return_value=mock_client,
    ):
        with patch("datascrapping.scrapers.places.search.time.sleep"):
            result = scraper.run(ctx)

    assert result.saved == 1
    assert result.errors == 0
    assert "completed" in result.message
    csv_path = result.output_path
    assert csv_path is not None and csv_path.exists()
    text = csv_path.read_text(encoding="utf-8")
    assert "Auditiva Campinas" in text
    assert "ChIJtest123" in text
    assert "(19) 3000-0000" in text
    seen_path = csv_path.parent / "places.seen.json"
    assert seen_path.exists()
    assert "ChIJtest123" in seen_path.read_text(encoding="utf-8")


def test_skip_seen_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    out = tmp_path / "places" / "campinas_sp_aasi"
    out.mkdir(parents=True)
    (out / "places.seen.json").write_text(
        json.dumps({"seen": ["ChIJtest123"]}) + "\n",
        encoding="utf-8",
    )

    scraper = PlacesSearchScraper()
    ctx = ScrapeContext(
        out_dir=tmp_path,
        extras={
            "city": "Campinas",
            "state": "SP",
            "niche": "aasi",
            "skip_geo_check": True,
        },
    )
    mock_client = MagicMock()
    mock_client.search_text_pages.return_value = [
        (_search_fields(), TEXT_SEARCH_QUOTA_COST)
    ]
    mock_client.get_details.return_value = _details_fields()

    with patch(
        "datascrapping.scrapers.places.search.PlacesClient",
        return_value=mock_client,
    ):
        with patch("datascrapping.scrapers.places.search.time.sleep"):
            # Force single-term niche via monkeypatch load_search_terms
            with patch(
                "datascrapping.scrapers.places.search.load_search_terms",
                return_value=["aparelhos auditivos"],
            ):
                result = scraper.run(ctx)

    assert result.saved == 0
    assert result.skipped >= 1
    mock_client.get_details.assert_not_called()


def test_quota_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    scraper = PlacesSearchScraper()
    # Only enough for one text search page, not details (32 < 32+17)
    ctx = ScrapeContext(
        out_dir=tmp_path,
        extras={
            "city": "Campinas",
            "state": "SP",
            "niche": "aasi",
            "skip_geo_check": True,
            "max_quota": TEXT_SEARCH_QUOTA_COST,
        },
    )
    mock_client = MagicMock()
    mock_client.search_text_pages.return_value = [
        (_search_fields(), TEXT_SEARCH_QUOTA_COST)
    ]

    with patch(
        "datascrapping.scrapers.places.search.PlacesClient",
        return_value=mock_client,
    ):
        with patch(
            "datascrapping.scrapers.places.search.load_search_terms",
            return_value=["aparelhos auditivos"],
        ):
            result = scraper.run(ctx)

    assert "partial_quota_exceeded" in result.message
    assert result.saved == 0
    mock_client.get_details.assert_not_called()
    assert PLACE_DETAILS_QUOTA_COST == 17


def test_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    scraper = PlacesSearchScraper()
    ctx = ScrapeContext(
        out_dir=tmp_path,
        extras={"city": "Campinas", "state": "SP", "skip_geo_check": True},
    )
    try:
        scraper.run(ctx)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "GOOGLE_PLACES_API_KEY" in str(exc)
