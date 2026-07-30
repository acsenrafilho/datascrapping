"""places.cnpj — enrich places_enriched.csv with BrasilAPI federal registry data."""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.checkpoint import SeenStore
from datascrapping.core.registry import register
from datascrapping.core.sinks import CsvSink
from datascrapping.scrapers.places.extract import (
    clean_cnpj_digits,
    format_cnpj,
    validate_cnpj,
)
from datascrapping.scrapers.places.federal import (
    RATE_LIMIT_DELAY,
    fetch_cnpj,
    map_federal_to_row,
    stamp_status,
)
from datascrapping.scrapers.places.models import (
    ENRICHED_CSV_FIELDS,
    FULL_CSV_FIELDS,
    base_row_from_enriched,
    cnpj_filters_from_extras,
    empty_full_extras,
    resolve_enriched_csv,
)

logger = logging.getLogger(__name__)


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{k: (v or "") for k, v in row.items()} for row in reader]


def _manual_row(cnpj_raw: str) -> dict[str, str]:
    digits = clean_cnpj_digits(cnpj_raw) or ""
    row = {key: "" for key in ENRICHED_CSV_FIELDS}
    row["place_id"] = f"manual-{digits or 'unknown'}"
    row["name"] = "manual"
    row["cnpj_raw"] = format_cnpj(digits) if digits else cnpj_raw
    return row


def _checkpoint_key(row: dict[str, str], digits: str | None) -> str:
    place_id = (row.get("place_id") or "").strip()
    if place_id:
        return place_id
    return digits or (row.get("cnpj_raw") or "").strip()


def _process_row(
    row: dict[str, str],
    *,
    sleep_fn=None,
    fetch_fn=None,
) -> dict[str, str]:
    sleep = sleep_fn or time.sleep
    fetch = fetch_fn or fetch_cnpj
    base = base_row_from_enriched(row)
    now = datetime.now(timezone.utc).isoformat()
    raw = (row.get("cnpj_raw") or "").strip()

    if not raw:
        extras = stamp_status(
            empty_full_extras(),
            status="skipped_empty",
            reason="Empty cnpj_raw",
            scraped_at=now,
        )
        return {**base, **extras}

    digits = clean_cnpj_digits(raw)
    if not digits or not validate_cnpj(digits):
        extras = stamp_status(
            empty_full_extras(),
            status="skipped_invalid",
            reason=f"Invalid CNPJ: {raw}",
            scraped_at=now,
        )
        return {**base, **extras}

    result = fetch(digits)
    extras = map_federal_to_row(result.data)
    stamp_status(
        extras,
        status=result.status,
        reason=result.reason,
        scraped_at=now,
    )
    sleep(RATE_LIMIT_DELAY)
    return {**base, **extras}


@register
class PlacesCnpjScraper(BaseScraper):
    name = "places.cnpj"
    description = (
        "Enrich places_enriched.csv via BrasilAPI CNPJ "
        "(razao_social, situacao, CNAE, endereço fiscal)"
    )

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        try:
            filters = cnpj_filters_from_extras(ctx.extras)
        except ValueError as exc:
            return ScrapeResult(scraper=self.name, errors=1, message=str(exc))

        # Mode: --cnpj alone (no --from)
        if filters.cnpj and not filters.from_path:
            out_dir = ctx.out_dir / "places" / "cnpj_manual"
            out_csv = out_dir / "places_full.csv"
            seen_path = out_dir / "places.cnpj.seen.json"
            rows = [_manual_row(filters.cnpj)]
            input_label = f"--cnpj {filters.cnpj}"
        else:
            try:
                input_csv = resolve_enriched_csv(filters.from_path)
            except ValueError as exc:
                return ScrapeResult(
                    scraper=self.name,
                    errors=1,
                    message=str(exc),
                )
            out_dir = input_csv.parent
            out_csv = out_dir / "places_full.csv"
            seen_path = out_dir / "places.cnpj.seen.json"
            rows = _read_csv_rows(input_csv) if input_csv.is_file() else []
            input_label = str(input_csv)

            # Optional: if --cnpj also set with --from, filter to that CNPJ only
            if filters.cnpj:
                target = clean_cnpj_digits(filters.cnpj) or filters.cnpj
                filtered = []
                for row in rows:
                    raw_digits = clean_cnpj_digits(row.get("cnpj_raw") or "") or ""
                    if raw_digits == target or (row.get("cnpj_raw") or "") == filters.cnpj:
                        filtered.append(row)
                if not filtered:
                    # Treat as single manual overlay on same out folder
                    rows = [_manual_row(filters.cnpj)]
                else:
                    rows = filtered

        if ctx.dry_run:
            with_cnpj = sum(1 for r in rows if (r.get("cnpj_raw") or "").strip())
            return ScrapeResult(
                scraper=self.name,
                saved=0,
                skipped=0,
                errors=0,
                output_path=out_csv,
                message=(
                    f"dry_run: would enrich {with_cnpj}/{len(rows)} rows "
                    f"with cnpj_raw from {input_label} → {out_csv}"
                ),
            )

        if not rows:
            return ScrapeResult(
                scraper=self.name,
                errors=1,
                message=f"No rows to process from {input_label}",
                output_path=out_csv,
            )

        out_dir.mkdir(parents=True, exist_ok=True)
        sink = CsvSink(out_csv, FULL_CSV_FIELDS)
        seen = SeenStore(seen_path)

        saved = 0
        skipped = 0
        errors = 0

        for row in rows:
            raw = (row.get("cnpj_raw") or "").strip()
            digits = clean_cnpj_digits(raw) if raw else None
            checkpoint_key = _checkpoint_key(row, digits)

            if checkpoint_key and checkpoint_key in seen:
                skipped += 1
                continue

            try:
                out_row = _process_row(row)
            except Exception as exc:  # noqa: BLE001 — keep batch alive
                logger.exception("CNPJ enrichment failed for %s", checkpoint_key)
                base = base_row_from_enriched(row)
                extras = stamp_status(
                    empty_full_extras(),
                    status="failed",
                    reason=f"Unexpected error: {exc}",
                )
                out_row = {**base, **extras}

            sink.write_rows([out_row])
            if checkpoint_key:
                seen.add(checkpoint_key)
                seen.save()

            if out_row.get("cnpj_status") == "failed":
                errors += 1
            else:
                saved += 1

        return ScrapeResult(
            scraper=self.name,
            saved=saved,
            skipped=skipped,
            errors=errors,
            output_path=out_csv,
            message=f"federal enrich → {out_csv}",
        )
