"""BNI Connect member search scraper.

Flow: authenticate → Search Category filters → API search pages →
enrich contacts from profiles → CSV with checkpoint/resume.
"""

from __future__ import annotations

import logging
from pathlib import Path

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.browser import BrowserUnavailableError, browser_session
from datascrapping.core.checkpoint import SeenStore
from datascrapping.core.rate_limit import polite_sleep
from datascrapping.core.registry import register
from datascrapping.core.sinks import CsvSink, sanitize_filename
from datascrapping.scrapers.bni.auth import ensure_authenticated
from datascrapping.scrapers.bni.models import CSV_FIELDS, filters_from_extras
from datascrapping.scrapers.bni.profile import enrich_member_contacts
from datascrapping.scrapers.bni.search import (
    apply_filters,
    estimate_result_cap_warning,
    search_members_page,
)

logger = logging.getLogger(__name__)

DEFAULT_BNI_DELAY_MIN = 3.0
DEFAULT_BNI_DELAY_MAX = 8.0


@register
class BniScraper(BaseScraper):
    name = "bni"
    description = (
        "BNI Connect member search → CSV "
        "(optional --specialty/--region/--country; see bni-specialties)"
    )

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        filters = filters_from_extras(ctx.extras)
        all_pages = bool(ctx.extras.get("all_pages"))
        headed = bool(ctx.extras.get("headed"))
        reauth = bool(ctx.extras.get("reauth"))

        delay_min = ctx.delay_min
        delay_max = ctx.delay_max
        if delay_min < DEFAULT_BNI_DELAY_MIN and ctx.extras.get(
            "delay_explicit"
        ) is not True:
            if delay_min == 1.0 and delay_max == 3.0:
                delay_min, delay_max = (
                    DEFAULT_BNI_DELAY_MIN,
                    DEFAULT_BNI_DELAY_MAX,
                )
                logger.info(
                    "Using BNI-safe delays: %.1f–%.1fs "
                    "(override with --delay-min/--delay-max)",
                    delay_min,
                    delay_max,
                )

        if all_pages:
            logger.warning(
                "--all-pages enabled: will walk every results page for this "
                "filter cut. Slower and higher risk of rate limits. "
                "BNI still caps a search at ~250 members; narrow with "
                "--specialty / --region if the result set is too broad."
            )
        if not filters.specialty:
            logger.warning(
                "No --specialty provided. Broader searches hit BNI's ~250 "
                "result cap sooner. List categories with: "
                "datascrapping bni-specialties"
            )

        region_part = filters.region or "all"
        specialty_part = filters.specialty or "all"
        run_slug = sanitize_filename(
            f"{filters.country}_{region_part}_{specialty_part}"
        )[:80]
        out_dir = Path(ctx.out_dir) / "bni" / run_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "members.csv"
        seen_path = out_dir / "members.seen.json"
        storage_path = Path(ctx.out_dir) / ".auth" / "bni_storage.json"

        seen = SeenStore(seen_path)
        sink = CsvSink(csv_path, CSV_FIELDS)

        saved = skipped = errors = 0

        try:
            with browser_session(
                headed=headed,
                storage_state=None if reauth else storage_path,
            ) as (_pw, _browser, context, page):
                ensure_authenticated(
                    page,
                    context,
                    storage_path=storage_path,
                    headed=headed,
                    reauth=reauth,
                )
                # UI search keeps session/locale warm; API drives collection.
                resolved = apply_filters(page, filters)

                page_index = 1
                total_pages = 1
                while True:
                    result_page = search_members_page(
                        page,
                        filters,
                        resolved,
                        page_no=page_index,
                    )
                    if page_index == 1:
                        estimate_result_cap_warning(result_page.total_results)
                        total_pages = max(1, result_page.total_pages)
                        logger.info(
                            "BNI search: %s members across %s page(s)",
                            result_page.total_results,
                            total_pages,
                        )

                    members = result_page.members
                    if not members:
                        logger.warning(
                            "No members returned by search API on page %s",
                            page_index,
                        )

                    for index, member in enumerate(members, start=1):
                        key = member.profile_url or member.name
                        if key in seen:
                            skipped += 1
                            logger.info("[SKIP] already collected %s", key)
                            continue

                        logger.info(
                            "[PROFILE] page=%s %s/%s %s",
                            page_index,
                            index,
                            len(members),
                            member.name or key,
                        )
                        if ctx.dry_run:
                            skipped += 1
                            continue

                        polite_sleep(delay_min, delay_max)
                        try:
                            enrich_member_contacts(page, member)
                            if filters.specialty and not member.specialty:
                                member.specialty = filters.specialty
                            if filters.country and not member.country:
                                member.country = filters.country
                            sink.write_rows([member.to_row()])
                            seen.add(key)
                            seen.save()
                            saved += 1
                        except Exception:
                            logger.exception(
                                "Failed profile %s", member.profile_url
                            )
                            errors += 1

                    if not all_pages:
                        break
                    if page_index >= total_pages:
                        logger.info("No further results pages")
                        break
                    page_index += 1
                    polite_sleep(delay_min, delay_max)

        except BrowserUnavailableError:
            raise
        except ValueError:
            raise

        return ScrapeResult(
            scraper=self.name,
            saved=saved,
            skipped=skipped,
            errors=errors,
            output_path=out_dir,
            message=(
                f"BNI cut region={filters.region!r} / "
                f"specialty={filters.specialty!r}: "
                f"saved={saved} skipped={skipped} errors={errors} "
                f"csv={csv_path}"
            ),
        )
