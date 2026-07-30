"""BNI Connect member search scraper.

Flow: authenticate → Search Category filters → API search pages →
enrich contacts from profiles → CSV with checkpoint/resume.

Note: BNI's advanced search API only filters on speciality_id. A
--category cut is expanded into one search per specialty under that group.
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
from datascrapping.scrapers.bni.categories import (
    expand_search_targets,
    fetch_category_catalog,
)
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
        "(optional --specialty/--category/--region/--country/--locale; "
        "see bni-specialties)"
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
                "BNI still caps each specialty search near ~250 members."
            )
        if not filters.specialty and not filters.category:
            logger.warning(
                "No --specialty or --category provided. Unfiltered searches "
                "return a broad directory dump (API reports up to 10000). "
                "Prefer --specialty or --category. "
                "List options: datascrapping bni-specialties / --groups-only"
            )
        if filters.locale:
            logger.info(
                "Using --locale %s for API labels only; geography is "
                "controlled by --country / --region",
                filters.locale,
            )

        region_part = filters.region or "all"
        focus_part = filters.specialty or filters.category or "all"
        slug_parts = [filters.country, region_part, focus_part]
        if filters.locale:
            slug_parts.append(filters.locale)
        run_slug = sanitize_filename("_".join(slug_parts))[:80]
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
                catalog = None
                if resolved is not None and resolved.is_primary_only:
                    catalog = fetch_category_catalog(
                        page.context,
                        preferred_locale=filters.locale,
                    )
                targets = expand_search_targets(resolved, catalog)

                for target_index, target in enumerate(targets, start=1):
                    target_label = (
                        target.display
                        if target is not None
                        else "(unfiltered)"
                    )
                    logger.info(
                        "Search target %s/%s: %s",
                        target_index,
                        len(targets),
                        target_label,
                    )

                    page_index = 1
                    total_pages = 1
                    while True:
                        result_page = search_members_page(
                            page,
                            filters,
                            target,
                            page_no=page_index,
                        )
                        if page_index == 1:
                            estimate_result_cap_warning(
                                result_page.total_results
                            )
                            total_pages = max(1, result_page.total_pages)
                            # Guard: category_id-only style dumps look like 10000
                            if (
                                target is not None
                                and result_page.total_results >= 10000
                            ):
                                raise RuntimeError(
                                    "BNI search returned an unfiltered dump "
                                    f"({result_page.total_results} results) for "
                                    f"{target_label!r}. Refusing to continue. "
                                    "Use --specialty or --category "
                                    "(category expands into specialties)."
                                )
                            logger.info(
                                "BNI search %r: %s members across %s page(s)",
                                target_label,
                                result_page.total_results,
                                total_pages,
                            )

                        members = result_page.members
                        if not members:
                            logger.warning(
                                "No members returned by search API on "
                                "target=%s page=%s",
                                target_label,
                                page_index,
                            )

                        for index, member in enumerate(members, start=1):
                            key = member.profile_url or member.name
                            if key in seen:
                                skipped += 1
                                logger.info(
                                    "[SKIP] already collected %s", key
                                )
                                continue

                            logger.info(
                                "[PROFILE] target=%s page=%s %s/%s %s",
                                target_index,
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
                                if (
                                    filters.specialty
                                    and not member.specialty
                                ):
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
                            logger.info(
                                "No further results pages for %r",
                                target_label,
                            )
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
                f"category={filters.category!r} / "
                f"specialty={filters.specialty!r} / "
                f"locale={filters.locale!r}: "
                f"saved={saved} skipped={skipped} errors={errors} "
                f"csv={csv_path}"
            ),
        )
