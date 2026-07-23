from __future__ import annotations

import logging

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.registry import register, registry

logger = logging.getLogger(__name__)


@register
class BlogAllScraper(BaseScraper):
    name = "blog.all"
    description = "Run the migrated competitor blog scrapers in sequence"

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        # Former scrap_looping.py targets (+ auditik)
        jobs: list[tuple[str, dict]] = [
            ("blog.communicare", {}),
            (
                "blog.concorrente",
                {
                    "url": "https://www.direitodeouvir.com.br/blog",
                    "out": "direito_ouvir",
                },
            ),
            ("blog.otoclinic", {}),
            ("blog.essencial", {}),
            ("blog.sonorita", {}),
            ("blog.auditik", {}),
        ]

        total_saved = total_skipped = total_errors = 0
        for name, extras in jobs:
            logger.info("=== Running %s ===", name)
            scraper_cls = registry.get(name)
            child_ctx = ScrapeContext(
                out_dir=ctx.out_dir,
                delay_min=ctx.delay_min,
                delay_max=ctx.delay_max,
                dry_run=ctx.dry_run,
                extras={**ctx.extras, **extras},
            )
            result = scraper_cls().run(child_ctx)
            total_saved += result.saved
            total_skipped += result.skipped
            total_errors += result.errors

        return ScrapeResult(
            scraper=self.name,
            saved=total_saved,
            skipped=total_skipped,
            errors=total_errors,
            output_path=ctx.out_dir,
            message=(
                f"blog.all finished: saved={total_saved} "
                f"skipped={total_skipped} errors={total_errors}"
            ),
        )
