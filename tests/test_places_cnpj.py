"""End-to-end places.cnpj scraper tests (BrasilAPI mocked)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch

from datascrapping.core.base import ScrapeContext
from datascrapping.scrapers.places.cnpj import PlacesCnpjScraper
from datascrapping.scrapers.places.federal import FederalFetchResult
from datascrapping.scrapers.places.models import ENRICHED_CSV_FIELDS, FULL_CSV_FIELDS

FIXTURE = (
    Path(__file__).parent / "fixtures" / "places" / "cnpj_ativa.json"
)

# Valid check-digit CNPJ used in fixtures / smoke
VALID_CNPJ = "19131243000197"
VALID_CNPJ_FMT = "19.131.243/0001-97"


def _write_enriched_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENRICHED_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in ENRICHED_CSV_FIELDS})


def _ok_fetch(_cnpj: str, **_kwargs) -> FederalFetchResult:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return FederalFetchResult(
        data=data,
        status="completed",
        reason="Successfully fetched federal data",
    )


def test_dry_run(tmp_path):
    csv_path = tmp_path / "places_enriched.csv"
    _write_enriched_csv(
        csv_path,
        [
            {"place_id": "p1", "name": "A", "cnpj_raw": VALID_CNPJ_FMT},
            {"place_id": "p2", "name": "B", "cnpj_raw": ""},
        ],
    )
    result = PlacesCnpjScraper().run(
        ScrapeContext(
            out_dir=tmp_path,
            dry_run=True,
            extras={"from_path": str(csv_path)},
        )
    )
    assert result.saved == 0
    assert "dry_run" in result.message
    assert "1/2" in result.message


def test_skip_empty_and_invalid(tmp_path):
    csv_path = tmp_path / "places_enriched.csv"
    _write_enriched_csv(
        csv_path,
        [
            {"place_id": "p1", "name": "Empty", "cnpj_raw": ""},
            {"place_id": "p2", "name": "Bad", "cnpj_raw": "123"},
            {"place_id": "p3", "name": "BadDigits", "cnpj_raw": "11111111111111"},
        ],
    )
    with patch(
        "datascrapping.scrapers.places.cnpj.fetch_cnpj",
        side_effect=AssertionError("should not call API"),
    ):
        result = PlacesCnpjScraper().run(
            ScrapeContext(
                out_dir=tmp_path,
                extras={"from_path": str(csv_path)},
            )
        )
    assert result.saved == 3
    assert result.errors == 0
    out = tmp_path / "places_full.csv"
    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["cnpj_status"] == "skipped_empty"
    assert rows[1]["cnpj_status"] == "skipped_invalid"
    assert rows[2]["cnpj_status"] == "skipped_invalid"
    assert set(rows[0].keys()) == set(FULL_CSV_FIELDS)


def test_enrich_success_from_folder(tmp_path):
    folder = tmp_path / "campinas_sp_aasi"
    csv_path = folder / "places_enriched.csv"
    _write_enriched_csv(
        csv_path,
        [
            {
                "place_id": "p1",
                "name": "Clinica",
                "email": "a@x.com",
                "cnpj_raw": VALID_CNPJ_FMT,
            }
        ],
    )
    with patch(
        "datascrapping.scrapers.places.cnpj.fetch_cnpj",
        side_effect=_ok_fetch,
    ), patch(
        "datascrapping.scrapers.places.cnpj.time.sleep",
        return_value=None,
    ):
        result = PlacesCnpjScraper().run(
            ScrapeContext(
                out_dir=tmp_path,
                extras={"from_path": str(folder)},
            )
        )
    assert result.saved == 1
    assert result.errors == 0
    out = folder / "places_full.csv"
    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["email"] == "a@x.com"
    assert rows[0]["razao_social"] == "OPEN KNOWLEDGE BRASIL"
    assert rows[0]["situacao"] == "ATIVA"
    assert rows[0]["cnae"] == "9430800"
    assert "SAO PAULO" in rows[0]["fiscal_endereco"]
    assert rows[0]["cnpj_status"] == "completed"


def test_checkpoint_resume(tmp_path):
    csv_path = tmp_path / "places_enriched.csv"
    _write_enriched_csv(
        csv_path,
        [
            {"place_id": "p1", "name": "A", "cnpj_raw": VALID_CNPJ_FMT},
            {"place_id": "p2", "name": "B", "cnpj_raw": VALID_CNPJ_FMT},
        ],
    )
    seen = tmp_path / "places.cnpj.seen.json"
    seen.write_text(json.dumps(["p1"]), encoding="utf-8")

    with patch(
        "datascrapping.scrapers.places.cnpj.fetch_cnpj",
        side_effect=_ok_fetch,
    ) as mocked, patch(
        "datascrapping.scrapers.places.cnpj.time.sleep",
        return_value=None,
    ):
        result = PlacesCnpjScraper().run(
            ScrapeContext(
                out_dir=tmp_path,
                extras={"from_path": str(csv_path)},
            )
        )
    assert result.skipped == 1
    assert result.saved == 1
    assert mocked.call_count == 1


def test_cnpj_single_mode(tmp_path):
    with patch(
        "datascrapping.scrapers.places.cnpj.fetch_cnpj",
        side_effect=_ok_fetch,
    ), patch(
        "datascrapping.scrapers.places.cnpj.time.sleep",
        return_value=None,
    ):
        result = PlacesCnpjScraper().run(
            ScrapeContext(
                out_dir=tmp_path,
                extras={"cnpj": VALID_CNPJ},
            )
        )
    assert result.saved == 1
    out = tmp_path / "places" / "cnpj_manual" / "places_full.csv"
    assert out.is_file()
    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["place_id"] == f"manual-{VALID_CNPJ}"
    assert rows[0]["razao_social"] == "OPEN KNOWLEDGE BRASIL"


def test_missing_from_and_cnpj():
    result = PlacesCnpjScraper().run(
        ScrapeContext(out_dir=Path("/tmp"), extras={})
    )
    assert result.errors == 1
    assert "--from" in result.message or "--cnpj" in result.message
