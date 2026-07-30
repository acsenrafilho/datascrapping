from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datascrapping.core.sinks import sanitize_filename

CSV_FIELDS = (
    "place_id",
    "name",
    "niche",
    "query_term",
    "city",
    "state",
    "phone",
    "phone_intl",
    "address",
    "email",
    "website",
    "lat",
    "lng",
    "maps_url",
    "rating",
    "user_ratings_total",
    "business_status",
    "types",
    "collected_at",
    "quota_units_est",
)

DEFAULT_NICHE = "aasi"
DEFAULT_MAX_QUOTA = 20000
TERMS_PATH = Path(__file__).with_name("terms.json")


@dataclass
class PlacesSearchFilters:
    city: str
    state: str
    niche: str = DEFAULT_NICHE
    skip_geo_check: bool = False
    max_quota: int = DEFAULT_MAX_QUOTA

    def validate(self) -> None:
        if not self.city:
            raise ValueError("Missing required --city for places.search")
        if not self.state:
            raise ValueError("Missing required --state (UF) for places.search")
        if len(self.state) != 2 or not self.state.isalpha():
            raise ValueError(
                f"Invalid --state {self.state!r}; expected a 2-letter UF (e.g. SP)"
            )
        if self.max_quota < 1:
            raise ValueError("--max-quota must be a positive integer")


@dataclass
class PlaceRow:
    place_id: str = ""
    name: str = ""
    niche: str = ""
    query_term: str = ""
    city: str = ""
    state: str = ""
    phone: str = ""
    phone_intl: str = ""
    address: str = ""
    email: str = ""
    website: str = ""
    lat: str = ""
    lng: str = ""
    maps_url: str = ""
    rating: str = ""
    user_ratings_total: str = ""
    business_status: str = ""
    types: str = ""
    collected_at: str = ""
    quota_units_est: str = ""

    def to_row(self) -> dict[str, str]:
        if not self.collected_at:
            self.collected_at = datetime.now(timezone.utc).isoformat()
        # email is reserved for places.website — always empty in stage 1
        self.email = ""
        data = asdict(self)
        return {key: str(data.get(key, "") or "") for key in CSV_FIELDS}


def filters_from_extras(extras: dict[str, Any]) -> PlacesSearchFilters:
    city = str(extras.get("city") or "").strip()
    state = str(extras.get("state") or "").strip().upper()
    niche = str(extras.get("niche") or DEFAULT_NICHE).strip().lower() or DEFAULT_NICHE
    skip_geo = bool(extras.get("skip_geo_check", False))
    max_quota_raw = extras.get("max_quota", DEFAULT_MAX_QUOTA)
    try:
        max_quota = int(max_quota_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid --max-quota {max_quota_raw!r}") from exc

    filters = PlacesSearchFilters(
        city=city,
        state=state,
        niche=niche,
        skip_geo_check=skip_geo,
        max_quota=max_quota,
    )
    filters.validate()
    return filters


def run_slug(city: str, state: str, niche: str) -> str:
    city_part = sanitize_filename(city).lower().replace(" ", "_")
    city_part = re.sub(r"_+", "_", city_part).strip("_") or "city"
    return f"{city_part}_{state.lower()}_{niche.lower()}"


def load_search_terms(niche: str, terms_path: Path | None = None) -> list[str]:
    path = terms_path or TERMS_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if niche not in data:
        raise ValueError(
            f"Unknown niche {niche!r}. Known: {', '.join(sorted(data.keys()))}"
        )
    terms = data[niche]
    if not isinstance(terms, list) or not terms:
        raise ValueError(
            f"No search terms configured for niche {niche!r} "
            f"(status: failed_no_search_terms)"
        )
    return [str(t).strip() for t in terms if str(t).strip()]


def known_niches(terms_path: Path | None = None) -> list[str]:
    path = terms_path or TERMS_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    return sorted(data.keys())
