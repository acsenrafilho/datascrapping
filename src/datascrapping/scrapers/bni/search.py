from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

from datascrapping.scrapers.bni.categories import (
    BniCategory,
    fetch_category_catalog,
    resolve_search_filters,
)
from datascrapping.scrapers.bni.models import BNI_SEARCH_URL, BniFilters, BniMember

logger = logging.getLogger(__name__)

BNI_SEARCH_API = (
    "https://api.bniconnectglobal.com/connect-search-api/search/member/advanced"
)

PROFILE_HREF_HINTS = (
    "/web/member",
    "/web/secure/networkhome",
    "/memberprofile",
    "/member-profile",
    "/profile/",
    "memberid=",
    "userid=",
)


@dataclass
class SearchPage:
    page_no: int
    total_pages: int
    total_results: int
    members: list[BniMember]
    resolved: BniCategory | None


def open_filter_panel(page) -> None:
    page.goto(BNI_SEARCH_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    filter_btn = page.get_by_role(
        "button", name=re.compile(r"^(Filter|Filtro)$", re.I)
    )
    if filter_btn.count() == 0:
        filter_btn = page.get_by_role(
            "button", name=re.compile(r"Filter|Filtro", re.I)
        )
    if filter_btn.count() == 0:
        raise RuntimeError(
            "Could not find BNI Filter button on search page. "
            "Try --headed to inspect the UI."
        )
    filter_btn.first.click()
    page.get_by_placeholder(
        re.compile(r"Search Category|Pesquisar Categoria", re.I)
    ).first.wait_for(state="visible", timeout=15_000)
    page.wait_for_timeout(400)


def _select_mui_autocomplete(page, placeholder: str, value: str) -> bool:
    """Type into a MUI Autocomplete and click the matching option."""
    field = page.get_by_placeholder(re.compile(placeholder, re.I)).first
    if field.count() == 0:
        return False
    field.click()
    field.fill("")
    field.type(value, delay=25)
    page.wait_for_timeout(800)

    options = page.locator('[role="listbox"] [role="option"], [role="option"]')
    try:
        options.first.wait_for(state="visible", timeout=8_000)
    except Exception:
        root = field.locator(
            "xpath=ancestor::*[contains(@class,'MuiAutocomplete-root')][1]"
        )
        open_btn = root.locator(
            'button[aria-label="Open"], button[aria-label="Abrir"]'
        )
        if open_btn.count():
            open_btn.click()
            page.wait_for_timeout(800)
            field.fill("")
            field.type(value, delay=25)
            page.wait_for_timeout(800)

    count = options.count()
    if count == 0:
        return False

    value_re = re.compile(re.escape(value), re.I)
    for index in range(count):
        option = options.nth(index)
        try:
            text = option.inner_text().strip()
        except Exception:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        secondary = lines[-1] if lines else text
        if value_re.fullmatch(secondary) or value_re.fullmatch(text):
            option.click()
            page.wait_for_timeout(400)
            return True
        if value_re.search(secondary) or value_re.search(text):
            option.click()
            page.wait_for_timeout(400)
            return True

    if count == 1:
        options.first.click()
        page.wait_for_timeout(400)
        return True
    return False


def apply_filters(page, filters: BniFilters) -> BniCategory | None:
    """Open Filter UI, apply optional country/region/specialty, run search.

    Returns the resolved Search Category or primary category group used for
    API queries (when --specialty and/or --category were provided).
    """
    open_filter_panel(page)

    country_ok = _select_mui_autocomplete(
        page,
        r"Select Country|Selecionar Pa[ií]s",
        filters.country,
    )
    if not country_ok and filters.country.casefold() == "brazil":
        country_ok = _select_mui_autocomplete(
            page,
            r"Select Country|Selecionar Pa[ií]s",
            "Brasil",
        )

    region_ok = False
    if filters.region:
        state = page.get_by_placeholder(
            re.compile(r"^(State|Estado)$", re.I)
        ).first
        if state.count():
            state.fill(filters.region)
            region_ok = True
        else:
            region_ok = _select_mui_autocomplete(
                page,
                r"State|Province|Region|Estado",
                filters.region,
            )

    resolved: BniCategory | None = None
    specialty_ok = True
    if filters.specialty or filters.category:
        catalog = fetch_category_catalog(
            page.context,
            preferred_locale=filters.locale,
        )
        resolved = resolve_search_filters(
            catalog,
            specialty=filters.specialty,
            category=filters.category,
        )

    if filters.specialty and resolved is not None and not resolved.is_primary_only:
        specialty_candidates = [resolved.secondary]
        if filters.specialty.strip().casefold() != resolved.secondary.casefold():
            specialty_candidates.append(filters.specialty.strip())
        specialty_ok = False
        for candidate in specialty_candidates:
            specialty_ok = _select_mui_autocomplete(
                page,
                r"Search Category|Pesquisar Categoria",
                candidate,
            )
            if specialty_ok:
                break

    logger.info(
        "Filter fill status: country=%s region=%s specialty=%s "
        "category=%s (resolved=%r)",
        country_ok,
        region_ok if filters.region else "skipped",
        specialty_ok if filters.specialty else "skipped",
        "api" if (filters.category and not filters.specialty) else (
            "hint" if filters.category else "skipped"
        ),
        resolved.display if resolved else None,
    )
    if not country_ok:
        raise RuntimeError(
            "Could not apply BNI country filter. "
            "Run with --headed to inspect the Filter panel."
        )
    if filters.region and not region_ok:
        raise RuntimeError(
            "Could not apply optional BNI --region filter. "
            "Run with --headed to inspect the Filter panel."
        )
    # Collection uses connect-search-api with speciality_id / category expansion.
    # UI autocomplete is best-effort only (locale labels often differ).
    if filters.specialty and not specialty_ok:
        if resolved is not None and resolved.secondary_id:
            logger.warning(
                "Could not select Search Category %r in the Filter UI; "
                "continuing with API speciality_id=%s (%s)",
                resolved.secondary,
                resolved.secondary_id,
                resolved.display,
            )
        else:
            raise RuntimeError(
                f"Could not resolve BNI Search Category {filters.specialty!r}. "
                "List options with: poetry run datascrapping bni-specialties."
            )

    search_btn = page.get_by_role(
        "button",
        name=re.compile(r"Search Members|Buscar Membros|^Search$|^Buscar$", re.I),
    ).first
    if search_btn.count():
        search_btn.click()
    else:
        page.keyboard.press("Enter")

    page.wait_for_timeout(2500)
    try:
        page.wait_for_load_state("networkidle")
    except Exception:
        pass
    return resolved


def _portal_access_token(page) -> str:
    raw = page.evaluate(
        "() => localStorage.getItem('bniconnect:portal:session')"
    )
    if not raw:
        raise RuntimeError(
            "BNI session token missing from localStorage; try --reauth"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Could not parse BNI portal session") from exc
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("BNI access_token missing; try --reauth")
    return token


def _portal_locale(page) -> str:
    raw = page.evaluate(
        "() => localStorage.getItem('bniconnect:portal:parameters')"
    )
    if not raw:
        return "en"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "en"
    return str(payload.get("locale") or "en")


def member_from_search_hit(hit: dict[str, Any]) -> BniMember:
    first = str(hit.get("first_name") or "").strip()
    last = str(hit.get("last_name") or "").strip()
    name = f"{first} {last}".strip()
    city = str(hit.get("city") or "").strip()
    state = str(hit.get("state") or "").strip()
    if city and state and state.casefold() not in city.casefold():
        city = f"{city}, {state}"
    elif not city and state:
        city = state

    specialty = str(hit.get("speciality") or "").strip()
    category = str(hit.get("category") or "").strip()
    if specialty and category:
        specialty_out = f"{category} > {specialty}"
    else:
        specialty_out = specialty or category

    profile_url = str(hit.get("profile_url") or "").strip()
    user_id = hit.get("user_id")
    if not profile_url and user_id is not None:
        profile_url = (
            "https://www.bniconnectglobal.com/web/secure/networkHome"
            f"?userId={user_id}"
        )

    return BniMember(
        name=name,
        company=str(hit.get("company_name") or "").strip(),
        chapter=str(hit.get("chapter_name") or "").strip(),
        city=city,
        country=str(hit.get("country") or "").strip(),
        specialty=specialty_out,
        profile_url=profile_url,
    )


def search_members_page(
    page,
    filters: BniFilters,
    resolved: BniCategory | None,
    *,
    page_no: int = 1,
    per_page: int = 20,
) -> SearchPage:
    """Query connect-search-api advanced member search for one page."""
    token = _portal_access_token(page)
    locale = filters.locale or _portal_locale(page)
    payload = {
        "search_tags": "",
        "country": filters.country,
        "first_name": None,
        "city": "",
        "last_name": None,
        "state": filters.region,
        "company_name": None,
        "category_id": resolved.primary_id if resolved else None,
        "speciality_id": (
            resolved.secondary_id
            if resolved and resolved.secondary_id
            else None
        ),
        "locale_code": locale,
        "concept_id": 1,
        "page_no": page_no,
        "per_page": per_page,
    }
    logger.info(
        "Search API request page=%s country=%r state=%r "
        "category_id=%s speciality_id=%s locale_code=%s",
        page_no,
        filters.country,
        filters.region,
        payload["category_id"],
        payload["speciality_id"],
        locale,
    )
    response = page.context.request.post(
        BNI_SEARCH_API,
        data=json.dumps(payload),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
    )
    if not response.ok:
        raise RuntimeError(
            f"BNI member search API failed ({response.status}) "
            f"on page {page_no}"
        )
    body = response.json()
    content = body.get("content") if isinstance(body, dict) else None
    if not isinstance(content, dict):
        raise RuntimeError("Unexpected BNI search API payload")

    hits = content.get("search_results") or []
    members = [
        member_from_search_hit(hit)
        for hit in hits
        if isinstance(hit, dict)
    ]
    total_pages = int(content.get("total_pages") or 1)
    total_results = int(content.get("total_results") or len(members))
    logger.info(
        "Search API page %s/%s: %s members (total_results=%s)",
        page_no,
        total_pages,
        len(members),
        total_results,
    )
    return SearchPage(
        page_no=page_no,
        total_pages=total_pages,
        total_results=total_results,
        members=members,
        resolved=resolved,
    )


def collect_profile_links_on_page(page) -> list[str]:
    """Fallback DOM collector for profile/networkHome anchors."""
    hrefs: set[str] = set()
    anchors = page.locator("a[href]")
    count = anchors.count()
    for index in range(count):
        try:
            href = anchors.nth(index).get_attribute("href") or ""
        except Exception:
            continue
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        absolute = urljoin(page.url, href)
        lower = absolute.lower()
        if any(hint in lower for hint in PROFILE_HREF_HINTS):
            hrefs.add(absolute.split("#")[0])
            continue
        parsed = urlparse(absolute)
        if "bniconnectglobal.com" in parsed.netloc and re.search(
            r"/member|networkhome|/profile", parsed.path, re.I
        ):
            hrefs.add(absolute.split("#")[0])

    links = sorted(hrefs)
    logger.info("Found %s profile links on current results page", len(links))
    return links


def go_to_next_results_page(page) -> bool:
    """Click next pagination control if present. Returns False if none."""
    candidates = [
        page.get_by_role("link", name=re.compile(r"^\s*next\s*$", re.I)),
        page.get_by_role("button", name=re.compile(r"^\s*next\s*$", re.I)),
        page.get_by_role(
            "button", name=re.compile(r"próximo|proximo|next", re.I)
        ),
        page.get_by_role("link", name=re.compile(r"próximo|proximo|>|»", re.I)),
        page.locator('a[aria-label*="next" i]'),
        page.locator('button[aria-label*="next" i]'),
        page.locator(".pagination a.next, li.next a, a.page-next"),
    ]
    for locator in candidates:
        try:
            target = locator.first
            if target.count() == 0:
                continue
            if not target.is_enabled():
                continue
            disabled = target.get_attribute("aria-disabled")
            if disabled and disabled.lower() == "true":
                continue
            classes = (target.get_attribute("class") or "").lower()
            if "disabled" in classes:
                continue
            target.click()
            page.wait_for_timeout(2000)
            page.wait_for_load_state("networkidle")
            return True
        except Exception:
            continue
    return False


def estimate_result_cap_warning(total_results: int | None = None) -> None:
    if total_results is not None and total_results >= 250:
        logger.warning(
            "BNI search returned %s results — directory search caps near 250. "
            "Narrow with --region if needed.",
            total_results,
        )
        return
    if total_results is not None:
        return
    logger.debug("Skipping DOM-based 250-result warning (API path)")
