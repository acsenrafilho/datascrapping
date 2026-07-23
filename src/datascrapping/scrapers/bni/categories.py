"""BNI Search Category (specialty) catalog via core-api."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import get_close_matches

logger = logging.getLogger(__name__)

BNI_CATEGORIES_API = (
    "https://api.bniconnectglobal.com/core-api/"
    "categories/primarySecondary/countryversion"
)

# UI autocomplete is English; resolve PT/ES labels to EN via secondaryId.
UI_LOCALE = "en"
LOOKUP_LOCALES = ("en", "pt_BR", "es")


@dataclass(frozen=True)
class BniCategory:
    primary_id: int
    secondary_id: int
    primary: str
    secondary: str
    description: str
    locale: str

    @property
    def label(self) -> str:
        return self.secondary

    @property
    def display(self) -> str:
        if self.primary:
            return f"{self.primary} > {self.secondary}"
        return self.secondary


def fetch_categories(context, *, locale: str = UI_LOCALE) -> list[BniCategory]:
    """Fetch specialty list for a locale using the authenticated browser context."""
    url = f"{BNI_CATEGORIES_API}?locale={locale}"
    response = context.request.get(url)
    if not response.ok:
        raise RuntimeError(
            f"BNI categories API failed ({response.status}) for locale={locale}"
        )
    payload = response.json()
    rows = payload.get("content") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected BNI categories API payload")

    categories: list[BniCategory] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        secondary = str(row.get("secondaryDescription") or "").strip()
        if not secondary:
            continue
        categories.append(
            BniCategory(
                primary_id=int(row.get("primaryId") or 0),
                secondary_id=int(row.get("secondaryId") or 0),
                primary=str(row.get("primaryDescription") or "").strip(),
                secondary=secondary,
                description=str(row.get("description") or "").strip(),
                locale=locale,
            )
        )
    logger.info("Loaded %s BNI categories (locale=%s)", len(categories), locale)
    return categories


def fetch_category_catalog(context) -> dict[str, list[BniCategory]]:
    catalog: dict[str, list[BniCategory]] = {}
    for locale in LOOKUP_LOCALES:
        try:
            catalog[locale] = fetch_categories(context, locale=locale)
        except Exception:
            logger.exception("Could not load BNI categories for locale=%s", locale)
    if UI_LOCALE not in catalog or not catalog[UI_LOCALE]:
        raise RuntimeError(
            "Could not load English BNI category list required for Search Category UI"
        )
    return catalog


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _match_score(query: str, category: BniCategory) -> int | None:
    """Higher is better; None = no match."""
    q = _norm(query)
    if not q:
        return None
    secondary = _norm(category.secondary)
    description = _norm(category.description)
    primary = _norm(category.primary)
    display = _norm(category.display)
    if q == secondary or q == description or q == display:
        return 100
    if q == primary:
        return 40
    if secondary.startswith(q) or description.startswith(q):
        return 80
    if q in secondary or q in description or q in display:
        return 70
    # token overlap for multi-word queries
    q_tokens = set(q.split())
    s_tokens = set(secondary.replace("/", " ").split())
    if q_tokens and q_tokens <= s_tokens:
        return 60
    return None


def find_category_matches(
    query: str,
    categories: list[BniCategory],
    *,
    limit: int = 15,
) -> list[BniCategory]:
    scored: list[tuple[int, BniCategory]] = []
    for category in categories:
        score = _match_score(query, category)
        if score is not None:
            scored.append((score, category))
    scored.sort(key=lambda item: (-item[0], item[1].secondary.casefold()))
    # de-dupe by secondary_id keeping best score
    seen: set[int] = set()
    out: list[BniCategory] = []
    for _score, category in scored:
        if category.secondary_id in seen:
            continue
        seen.add(category.secondary_id)
        out.append(category)
        if len(out) >= limit:
            break
    if out:
        return out

    # fuzzy fallback on secondary labels
    labels = [c.secondary for c in categories]
    close = get_close_matches(query, labels, n=limit, cutoff=0.55)
    by_label = {c.secondary: c for c in categories}
    return [by_label[label] for label in close if label in by_label]


def resolve_specialty(
    specialty: str,
    catalog: dict[str, list[BniCategory]],
    *,
    category_group: str | None = None,
) -> BniCategory:
    """Map a user specialty string (any locale) to the English UI category."""
    query = specialty.strip()
    if not query:
        raise ValueError("specialty is empty")

    en_by_id = {c.secondary_id: c for c in catalog.get(UI_LOCALE, [])}
    group = (category_group or "").strip()

    # Search all locales, prefer exact/high scores, then map to EN via secondary_id.
    candidates: list[tuple[int, BniCategory]] = []
    for _locale, categories in catalog.items():
        for category in categories:
            score = _match_score(query, category)
            if score is None:
                continue
            if group:
                group_n = _norm(group)
                if group_n == _norm(category.primary):
                    score += 20
                elif group_n in _norm(category.primary):
                    score += 10
            candidates.append((score, category))

    if not candidates:
        suggestions = find_category_matches(query, catalog.get(UI_LOCALE, []), limit=8)
        tip = ", ".join(f'"{s.secondary}"' for s in suggestions) or "(none)"
        raise ValueError(
            f"BNI specialty {specialty!r} is not in the Search Category list. "
            f"Suggestions: {tip}. "
            "List options with: poetry run datascrapping bni-specialties "
            f'--query "{specialty}"'
        )

    candidates.sort(key=lambda item: (-item[0], item[1].locale != UI_LOCALE))
    best = candidates[0][1]
    resolved = en_by_id.get(best.secondary_id, best)

    logger.info(
        "Resolved specialty %r → %s (secondaryId=%s)",
        specialty,
        resolved.display,
        resolved.secondary_id,
    )
    return resolved
