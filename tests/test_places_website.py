"""End-to-end places.website scraper tests (HTTP/Gemini mocked)."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

from datascrapping.core.base import ScrapeContext
from datascrapping.scrapers.places.crawl import CrawlResult, CrawlStats
from datascrapping.scrapers.places.models import CSV_FIELDS, ENRICHED_CSV_FIELDS
from datascrapping.scrapers.places.website import (
    PlacesWebsiteScraper,
    _merge_fill_gaps,
)
from datascrapping.scrapers.places.extract import HeuristicExtraction

HTML_PAGE = """
<html><head><title>Clinica Teste</title></head>
<body>
<a href="mailto:hello@clinicateste.com.br">mail</a>
<a href="https://instagram.com/clinicateste">ig</a>
</body></html>
"""


def _write_places_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def test_merge_heuristics_win_over_gemini():
    heur = HeuristicExtraction(
        emails=["a@x.com"],
        phones=["119999"],
        cnpj_raw="11.444.777/0001-61",
        social={"instagram": "https://instagram.com/a"},
        brand_name="Heur Brand",
    )
    gemini = {
        "emails": ["b@y.com"],
        "phones": [{"number": "118888", "type": "mobile"}],
        "cnpj": "00.000.000/0000-00",
        "brand_name": "Gemini Brand",
        "social_links": {
            "instagram": "https://instagram.com/gemini",
            "facebook": "https://facebook.com/gemini",
        },
    }
    email, extras = _merge_fill_gaps(heur, gemini)
    assert email == "a@x.com"
    assert "b@y.com" in extras["emails_extra"]
    assert extras["cnpj_raw"] == "11.444.777/0001-61"
    assert extras["brand_name"] == "Heur Brand"
    assert extras["social_instagram"] == "https://instagram.com/a"
    assert extras["social_facebook"] == "https://facebook.com/gemini"


def test_dry_run(tmp_path):
    csv_path = tmp_path / "places.csv"
    _write_places_csv(
        csv_path,
        [
            {
                "place_id": "p1",
                "name": "A",
                "website": "https://a.com",
            },
            {"place_id": "p2", "name": "B", "website": ""},
        ],
    )
    scraper = PlacesWebsiteScraper()
    result = scraper.run(
        ScrapeContext(
            out_dir=tmp_path,
            dry_run=True,
            extras={"from_path": str(csv_path), "skip_llm": True},
        )
    )
    assert result.saved == 0
    assert "dry_run" in result.message
    assert "1/2" in result.message


def test_skip_no_website(tmp_path):
    csv_path = tmp_path / "places.csv"
    _write_places_csv(
        csv_path,
        [{"place_id": "p1", "name": "NoWeb", "website": ""}],
    )
    scraper = PlacesWebsiteScraper()
    result = scraper.run(
        ScrapeContext(
            out_dir=tmp_path,
            extras={"from_path": str(csv_path), "skip_llm": True},
        )
    )
    assert result.saved == 1
    out = tmp_path / "places_enriched.csv"
    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["website_status"] == "skipped_no_website"
    assert rows[0]["email"] == ""
    assert set(rows[0].keys()) == set(ENRICHED_CSV_FIELDS)


def test_enrich_with_mocked_crawl(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    csv_path = tmp_path / "places.csv"
    _write_places_csv(
        csv_path,
        [
            {
                "place_id": "p1",
                "name": "Clinica",
                "city": "Campinas",
                "state": "SP",
                "website": "https://clinicateste.com.br",
            }
        ],
    )
    crawl = CrawlResult(
        pages={"https://clinicateste.com.br/": HTML_PAGE},
        stats=CrawlStats(pages_fetched=1, pages_failed=0),
        status="completed",
        base_url="https://clinicateste.com.br",
    )
    scraper = PlacesWebsiteScraper()
    with patch(
        "datascrapping.scrapers.places.website.WebsiteCrawler"
    ) as crawler_cls:
        crawler_cls.return_value.crawl.return_value = crawl
        result = scraper.run(
            ScrapeContext(
                out_dir=tmp_path,
                extras={"from_path": str(csv_path), "skip_llm": True},
            )
        )
    assert result.saved == 1
    out = tmp_path / "places_enriched.csv"
    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["email"] == "hello@clinicateste.com.br"
    assert rows[0]["social_instagram"]
    assert rows[0]["website_status"] == "completed"
    assert (tmp_path / "places.website.seen.json").exists()


def test_checkpoint_resume(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    csv_path = tmp_path / "places.csv"
    _write_places_csv(
        csv_path,
        [
            {
                "place_id": "p1",
                "name": "A",
                "website": "https://a.com",
            }
        ],
    )
    crawl = CrawlResult(
        pages={"https://a.com/": HTML_PAGE},
        stats=CrawlStats(pages_fetched=1),
        status="completed",
        base_url="https://a.com",
    )
    scraper = PlacesWebsiteScraper()
    ctx = ScrapeContext(
        out_dir=tmp_path,
        extras={"from_path": str(csv_path), "skip_llm": True},
    )
    with patch(
        "datascrapping.scrapers.places.website.WebsiteCrawler"
    ) as crawler_cls:
        crawler_cls.return_value.crawl.return_value = crawl
        first = scraper.run(ctx)
        second = scraper.run(ctx)
    assert first.saved == 1
    assert second.skipped == 1
    assert second.saved == 0


def test_gemini_fill_gaps_when_heuristics_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    csv_path = tmp_path / "places.csv"
    _write_places_csv(
        csv_path,
        [
            {
                "place_id": "p1",
                "name": "A",
                "website": "https://a.com",
            }
        ],
    )
    bare_html = "<html><body><p>Olá</p></body></html>"
    crawl = CrawlResult(
        pages={"https://a.com/": bare_html},
        stats=CrawlStats(pages_fetched=1),
        status="completed",
        base_url="https://a.com",
    )
    gemini_payload = {
        "emails": ["llm@a.com"],
        "brand_name": "Brand LLM",
        "cnpj": "11.444.777/0001-61",
        "social_links": {"linkedin": "https://linkedin.com/company/a"},
        "phones": [],
    }
    scraper = PlacesWebsiteScraper()
    with (
        patch(
            "datascrapping.scrapers.places.website.WebsiteCrawler"
        ) as crawler_cls,
        patch(
            "datascrapping.scrapers.places.website.extract_with_gemini",
            return_value=gemini_payload,
        ) as gemini_fn,
    ):
        crawler_cls.return_value.crawl.return_value = crawl
        result = scraper.run(
            ScrapeContext(
                out_dir=tmp_path,
                extras={"from_path": str(csv_path), "skip_llm": False},
            )
        )
    assert result.saved == 1
    gemini_fn.assert_called_once()
    with (tmp_path / "places_enriched.csv").open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert row["email"] == "llm@a.com"
    assert row["brand_name"] == "Brand LLM"
    assert row["cnpj_raw"] == "11.444.777/0001-61"
    assert row["social_linkedin"]


def test_from_folder_resolves_places_csv(tmp_path):
    csv_path = tmp_path / "run" / "places.csv"
    _write_places_csv(csv_path, [{"place_id": "p1", "website": ""}])
    scraper = PlacesWebsiteScraper()
    result = scraper.run(
        ScrapeContext(
            out_dir=tmp_path,
            extras={"from_path": str(tmp_path / "run"), "skip_llm": True},
        )
    )
    assert result.saved == 1
    assert (tmp_path / "run" / "places_enriched.csv").exists()


def test_missing_from_path():
    scraper = PlacesWebsiteScraper()
    try:
        scraper.run(ScrapeContext(out_dir=Path("/tmp"), extras={}))
        assert False, "expected ValueError from filters"
    except ValueError as exc:
        assert "--from" in str(exc)
