"""places.website — enrich places.csv with email/contact from company websites."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.checkpoint import SeenStore
from datascrapping.core.config import env
from datascrapping.core.registry import register
from datascrapping.core.sinks import CsvSink
from datascrapping.scrapers.places.crawl import WebsiteCrawler
from datascrapping.scrapers.places.extract import (
    HeuristicExtraction,
    extract_from_pages,
)
from datascrapping.scrapers.places.gemini import (
    GeminiUnavailable,
    extract_with_gemini,
)
from datascrapping.scrapers.places.models import (
    ENRICHED_CSV_FIELDS,
    base_row_from_places,
    empty_enriched_extras,
    join_extra,
    resolve_places_csv,
    website_filters_from_extras,
)

logger = logging.getLogger(__name__)


def _merge_fill_gaps(
    heur: HeuristicExtraction,
    gemini_data: dict[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    """Heuristic wins on filled fields; Gemini only fills empties.

    Returns (primary_email, enriched_extra_fields).
    """
    extras = empty_enriched_extras()

    emails = list(heur.emails)
    phones = list(heur.phones)
    cnpj = heur.cnpj_raw
    brand = heur.brand_name
    social = dict(heur.social)

    if gemini_data:
        for email in gemini_data.get("emails") or []:
            if isinstance(email, str) and email.strip():
                emails.append(email.strip().lower())
        for phone_item in gemini_data.get("phones") or []:
            if isinstance(phone_item, dict):
                number = str(phone_item.get("number") or "").strip()
            else:
                number = str(phone_item or "").strip()
            if number:
                phones.append(number)
        if not cnpj and gemini_data.get("cnpj"):
            cnpj = str(gemini_data["cnpj"]).strip()
        if not brand and gemini_data.get("brand_name"):
            brand = str(gemini_data["brand_name"]).strip()
        links = gemini_data.get("social_links") or {}
        if isinstance(links, dict):
            for key in (
                "facebook",
                "instagram",
                "linkedin",
                "youtube",
                "tiktok",
                "twitter",
            ):
                if key not in social and links.get(key):
                    social[key] = str(links[key]).strip()

    # de-dupe emails after merge
    seen: set[str] = set()
    uniq_emails: list[str] = []
    for email in emails:
        key = email.lower().strip()
        if key and key not in seen:
            seen.add(key)
            uniq_emails.append(key)

    primary_email = uniq_emails[0] if uniq_emails else ""
    extras["emails_extra"] = join_extra(uniq_emails[1:])
    extras["phones_extra"] = join_extra(phones)
    extras["cnpj_raw"] = cnpj
    extras["brand_name"] = brand
    extras["social_facebook"] = social.get("facebook", "")
    extras["social_instagram"] = social.get("instagram", "")
    extras["social_linkedin"] = social.get("linkedin", "")
    extras["social_youtube"] = social.get("youtube", "")
    extras["social_tiktok"] = social.get("tiktok", "")
    extras["social_twitter"] = social.get("twitter", "")
    return primary_email, extras


def _read_places_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{k: (v or "") for k, v in row.items()} for row in reader]


@register
class PlacesWebsiteScraper(BaseScraper):
    name = "places.website"
    description = (
        "Enrich places.csv via website crawl (email heuristics + optional Gemini)"
    )

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        filters = website_filters_from_extras(ctx.extras)
        try:
            input_csv = resolve_places_csv(filters.from_path)
        except ValueError as exc:
            return ScrapeResult(
                scraper=self.name,
                errors=1,
                message=str(exc),
            )

        out_dir = input_csv.parent
        out_csv = out_dir / "places_enriched.csv"
        seen_path = out_dir / "places.website.seen.json"

        if ctx.dry_run:
            rows = _read_places_rows(input_csv) if input_csv.is_file() else []
            with_web = sum(1 for r in rows if (r.get("website") or "").strip())
            return ScrapeResult(
                scraper=self.name,
                saved=0,
                skipped=0,
                errors=0,
                output_path=out_csv,
                message=(
                    f"dry_run: would enrich {with_web}/{len(rows)} rows "
                    f"with website from {input_csv} → {out_csv} "
                    f"(skip_llm={filters.skip_llm})"
                ),
            )

        rows = _read_places_rows(input_csv)
        if not rows:
            return ScrapeResult(
                scraper=self.name,
                errors=1,
                message=f"No rows in {input_csv}",
                output_path=out_csv,
            )

        sink = CsvSink(out_csv, ENRICHED_CSV_FIELDS)
        seen = SeenStore(seen_path)
        use_llm = not filters.skip_llm
        gemini_key = env("GEMINI_API_KEY") if use_llm else ""

        saved = 0
        skipped = 0
        errors = 0

        for row in rows:
            place_id = (row.get("place_id") or "").strip()
            website = (row.get("website") or "").strip()
            checkpoint_key = place_id or website

            if checkpoint_key and checkpoint_key in seen:
                skipped += 1
                continue

            base = base_row_from_places(row)
            extras = empty_enriched_extras()
            now = datetime.now(timezone.utc).isoformat()

            if not website:
                extras["website_status"] = "skipped_no_website"
                extras["website_scraped_at"] = now
                out_row = {**base, **extras}
                out_row["email"] = ""
                sink.write_rows([out_row])
                if checkpoint_key:
                    seen.add(checkpoint_key)
                    seen.save()
                saved += 1
                continue

            try:
                crawler = WebsiteCrawler()
                crawl = crawler.crawl(website, polite=True)
            except Exception as exc:
                logger.exception("Crawl failed for %s", website)
                errors += 1
                extras["website_status"] = f"failed: {exc}"
                extras["website_scraped_at"] = now
                out_row = {**base, **extras}
                out_row["email"] = ""
                sink.write_rows([out_row])
                if checkpoint_key:
                    seen.add(checkpoint_key)
                    seen.save()
                continue

            heur = (
                extract_from_pages(crawl.pages)
                if crawl.pages
                else HeuristicExtraction()
            )

            gemini_data: dict[str, Any] | None = None
            if use_llm and gemini_key and crawl.pages:
                try:
                    gemini_data = extract_with_gemini(crawl.pages, gemini_key)
                except GeminiUnavailable as exc:
                    logger.warning("Gemini skipped: %s", exc)
                except Exception as exc:
                    logger.warning("Gemini extraction failed: %s", exc)

            email, merged = _merge_fill_gaps(heur, gemini_data)

            if crawl.status_reason == "Scraping disallowed by robots.txt":
                status = "robots_disallowed"
            elif crawl.status == "failed":
                status = "failed"
            elif not crawl.pages:
                status = f"partial:{crawl.status_reason or 'no_pages'}"
            elif crawl.status == "partial":
                status = "partial"
            else:
                status = "completed"

            out_row = {**base, **merged}
            out_row["email"] = email
            out_row["website_status"] = status
            out_row["website_scraped_at"] = now
            out_row["pages_fetched"] = str(crawl.stats.pages_fetched)
            out_row["pages_failed"] = str(crawl.stats.pages_failed)

            sink.write_rows([out_row])
            if checkpoint_key:
                seen.add(checkpoint_key)
                seen.save()
            saved += 1

        return ScrapeResult(
            scraper=self.name,
            saved=saved,
            skipped=skipped,
            errors=errors,
            output_path=out_csv,
            message=f"enriched → {out_csv}",
        )
