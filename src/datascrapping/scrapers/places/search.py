from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult
from datascrapping.core.checkpoint import SeenStore
from datascrapping.core.config import env
from datascrapping.core.registry import register
from datascrapping.core.sinks import CsvSink
from datascrapping.scrapers.places.client import (
    PLACE_DETAILS_QUOTA_COST,
    PlacesClient,
    merge_place_fields,
)
from datascrapping.scrapers.places.dedupe import should_skip_place
from datascrapping.scrapers.places.geo import GeoValidationError, validate_city_state
from datascrapping.scrapers.places.models import (
    CSV_FIELDS,
    PlaceRow,
    filters_from_extras,
    load_search_terms,
    run_slug,
)

logger = logging.getLogger(__name__)


@register
class PlacesSearchScraper(BaseScraper):
    name = "places.search"
    description = (
        "Google Places Text Search + Details → CSV (prospecção comercial)"
    )

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        filters = filters_from_extras(ctx.extras)
        city_display = filters.city.strip()
        state = filters.state

        if not filters.skip_geo_check:
            try:
                city_u, state = validate_city_state(city_display, state)
                # keep original casing for CSV city when possible
                city_for_query = city_display
                _ = city_u
            except GeoValidationError as exc:
                return ScrapeResult(
                    scraper=self.name,
                    errors=1,
                    message=f"failed_geo_check: {exc}",
                )
        else:
            city_for_query = city_display

        try:
            terms = load_search_terms(filters.niche)
        except ValueError as exc:
            return ScrapeResult(
                scraper=self.name,
                errors=1,
                message=str(exc),
            )

        slug = run_slug(city_display, state, filters.niche)
        out_dir = Path(ctx.out_dir) / "places" / slug
        csv_path = out_dir / "places.csv"
        seen_path = out_dir / "places.seen.json"

        if ctx.dry_run:
            return ScrapeResult(
                scraper=self.name,
                saved=0,
                skipped=0,
                errors=0,
                output_path=csv_path,
                message=(
                    f"dry_run: would search niche={filters.niche} "
                    f"city={city_for_query!r} state={state} "
                    f"terms={len(terms)} max_quota={filters.max_quota} "
                    f"→ {csv_path}"
                ),
            )

        api_key = env("GOOGLE_PLACES_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing GOOGLE_PLACES_API_KEY in environment /.env "
                "(use a prospection key, not the Lead Control product key)"
            )

        out_dir.mkdir(parents=True, exist_ok=True)
        sink = CsvSink(csv_path, CSV_FIELDS)
        seen = SeenStore(seen_path)
        client = PlacesClient(api_key)

        quota_used = 0
        saved = 0
        skipped = 0
        errors = 0
        accepted: list[dict[str, Any]] = []
        status = "completed"
        warned_80 = False
        warned_90 = False

        def _quota_ok(needed: int) -> bool:
            return quota_used + needed <= filters.max_quota

        def _quota_warn() -> None:
            nonlocal warned_80, warned_90
            ratio = quota_used / filters.max_quota if filters.max_quota else 0
            if ratio >= 0.9 and not warned_90:
                logger.warning(
                    "Places quota ≥90%% (%s / %s)",
                    quota_used,
                    filters.max_quota,
                )
                warned_90 = True
            elif ratio >= 0.8 and not warned_80:
                logger.info(
                    "Places quota ≥80%% (%s / %s)",
                    quota_used,
                    filters.max_quota,
                )
                warned_80 = True

        for term_idx, term in enumerate(terms):
            if not _quota_ok(PLACE_DETAILS_QUOTA_COST):
                # need at least one search page cost; check search cost below
                pass

            try:
                pages = client.search_text_pages(term, city_for_query, state)
            except Exception as exc:
                logger.error("Text search failed for term %r: %s", term, exc)
                errors += 1
                status = "failed_api_error"
                break

            stop_quota = False
            for page_places, page_cost in pages:
                if not _quota_ok(page_cost):
                    status = "partial_quota_exceeded"
                    stop_quota = True
                    break
                quota_used += page_cost
                _quota_warn()

                for place in page_places:
                    place_id = str(place.get("place_id") or "")
                    name = str(place.get("name") or "")
                    lat_s = place.get("lat")
                    lng_s = place.get("lng")
                    lat: float | None
                    lng: float | None
                    try:
                        lat = float(lat_s) if lat_s not in (None, "") else None
                        lng = float(lng_s) if lng_s not in (None, "") else None
                    except (TypeError, ValueError):
                        lat, lng = None, None

                    in_run_ids = {p["place_id"] for p in accepted}
                    if place_id in seen:
                        in_run_ids.add(place_id)
                    reason = should_skip_place(
                        place_id,
                        name,
                        lat,
                        lng,
                        in_run_ids,
                        accepted,
                    )
                    if reason:
                        skipped += 1
                        logger.debug("Skip %s (%s)", place_id, reason)
                        continue

                    if not _quota_ok(PLACE_DETAILS_QUOTA_COST):
                        status = "partial_quota_exceeded"
                        stop_quota = True
                        break

                    details = client.get_details(place_id)
                    quota_used += PLACE_DETAILS_QUOTA_COST
                    _quota_warn()
                    if details is None:
                        errors += 1
                        continue

                    merged = merge_place_fields(place, details)
                    row = PlaceRow(
                        place_id=str(merged.get("place_id") or place_id),
                        name=str(merged.get("name") or ""),
                        niche=filters.niche,
                        query_term=term,
                        city=city_display,
                        state=state,
                        phone=str(merged.get("phone") or ""),
                        phone_intl=str(merged.get("phone_intl") or ""),
                        address=str(merged.get("address") or ""),
                        website=str(merged.get("website") or ""),
                        lat=str(merged.get("lat") or ""),
                        lng=str(merged.get("lng") or ""),
                        maps_url=str(merged.get("maps_url") or ""),
                        rating=str(merged.get("rating") or ""),
                        user_ratings_total=str(
                            merged.get("user_ratings_total") or ""
                        ),
                        business_status=str(merged.get("business_status") or ""),
                        types=str(merged.get("types") or ""),
                        quota_units_est=str(quota_used),
                    )
                    sink.write_rows([row.to_row()], dry_run=False)
                    seen.add(row.place_id)
                    seen.save()
                    accepted.append(
                        {
                            "place_id": row.place_id,
                            "name": row.name,
                            "lat": row.lat,
                            "lng": row.lng,
                        }
                    )
                    saved += 1

                if stop_quota:
                    break

            if stop_quota or status == "failed_api_error":
                break

            if term_idx < len(terms) - 1:
                time.sleep(1)

        if status == "completed" and saved == 0:
            status = "completed_no_results"

        return ScrapeResult(
            scraper=self.name,
            saved=saved,
            skipped=skipped,
            errors=errors,
            output_path=csv_path,
            message=(
                f"{status}; quota_used_est={quota_used}/{filters.max_quota}; "
                f"terms={len(terms)}"
            ),
        )
