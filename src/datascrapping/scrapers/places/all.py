"""places.all — run places.search → places.website → places.cnpj for one city."""

from __future__ import annotations

import logging
from pathlib import Path

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.registry import register, registry
from datascrapping.scrapers.places.models import filters_from_extras, run_slug

logger = logging.getLogger(__name__)

STAGE_SEARCH = "places.search"
STAGE_WEBSITE = "places.website"
STAGE_CNPJ = "places.cnpj"


@register
class PlacesAllScraper(BaseScraper):
    name = "places.all"
    description = (
        "Run Places pipeline for one city: "
        "search → website → cnpj (single command)"
    )

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        # Validate search flags early (city/state/niche/quota).
        try:
            filters = filters_from_extras(ctx.extras)
        except ValueError as exc:
            return ScrapeResult(scraper=self.name, errors=1, message=str(exc))

        slug = run_slug(filters.city, filters.state, filters.niche)
        folder = Path(ctx.out_dir) / "places" / slug
        places_csv = folder / "places.csv"
        enriched_csv = folder / "places_enriched.csv"
        full_csv = folder / "places_full.csv"

        if ctx.dry_run:
            search_cls = registry.get(STAGE_SEARCH)
            search_result = search_cls().run(ctx)
            return ScrapeResult(
                scraper=self.name,
                saved=0,
                skipped=0,
                errors=search_result.errors,
                output_path=full_csv,
                message=(
                    f"dry_run places.all → {folder}: "
                    f"(1) {STAGE_SEARCH}; "
                    f"(2) {STAGE_WEBSITE} --from {folder}; "
                    f"(3) {STAGE_CNPJ} --from {folder}. "
                    f"{search_result.message}"
                ),
            )

        total_saved = total_skipped = total_errors = 0
        messages: list[str] = []

        def _run_stage(name: str, extras: dict) -> ScrapeResult:
            logger.info("=== places.all → %s ===", name)
            scraper_cls = registry.get(name)
            child_ctx = ScrapeContext(
                out_dir=ctx.out_dir,
                delay_min=ctx.delay_min,
                delay_max=ctx.delay_max,
                dry_run=False,
                extras=extras,
            )
            return scraper_cls().run(child_ctx)

        # ① search
        r1 = _run_stage(STAGE_SEARCH, dict(ctx.extras))
        total_saved += r1.saved
        total_skipped += r1.skipped
        total_errors += r1.errors
        messages.append(f"search: {r1.message or f'saved={r1.saved}'}")

        if not places_csv.is_file():
            return ScrapeResult(
                scraper=self.name,
                saved=total_saved,
                skipped=total_skipped,
                errors=max(total_errors, 1),
                output_path=r1.output_path,
                message=(
                    f"places.all aborted after {STAGE_SEARCH}: "
                    f"no {places_csv.name}. {'; '.join(messages)}"
                ),
            )

        # ② website (from_path = city folder)
        website_extras = {
            "from_path": str(folder),
            "skip_llm": bool(ctx.extras.get("skip_llm", False)),
        }
        r2 = _run_stage(STAGE_WEBSITE, website_extras)
        total_saved += r2.saved
        total_skipped += r2.skipped
        total_errors += r2.errors
        messages.append(f"website: {r2.message or f'saved={r2.saved}'}")

        if not enriched_csv.is_file():
            return ScrapeResult(
                scraper=self.name,
                saved=total_saved,
                skipped=total_skipped,
                errors=max(total_errors, 1),
                output_path=r2.output_path or places_csv,
                message=(
                    f"places.all aborted after {STAGE_WEBSITE}: "
                    f"no {enriched_csv.name}. {'; '.join(messages)}"
                ),
            )

        # ③ cnpj
        r3 = _run_stage(STAGE_CNPJ, {"from_path": str(folder)})
        total_saved += r3.saved
        total_skipped += r3.skipped
        total_errors += r3.errors
        messages.append(f"cnpj: {r3.message or f'saved={r3.saved}'}")

        return ScrapeResult(
            scraper=self.name,
            saved=total_saved,
            skipped=total_skipped,
            errors=total_errors,
            output_path=full_csv if full_csv.is_file() else r3.output_path,
            message=(
                f"places.all finished → {full_csv if full_csv.is_file() else folder}. "
                + " | ".join(messages)
            ),
        )
