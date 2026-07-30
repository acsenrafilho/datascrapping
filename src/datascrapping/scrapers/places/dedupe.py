from __future__ import annotations

import math
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

DUPLICATE_DISTANCE_THRESHOLD_METERS = 50
NAME_SIMILARITY_THRESHOLD = 0.90
EARTH_RADIUS_METERS = 6371000


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def name_similarity(name1: str, name2: str) -> float:
    if not name1 or not name2:
        return 0.0
    return SequenceMatcher(None, name1.lower().strip(), name2.lower().strip()).ratio()


def _coords(place: Mapping[str, Any]) -> tuple[float, float] | None:
    lat = place.get("lat")
    lng = place.get("lng")
    if lat is None or lng is None or lat == "" or lng == "":
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def is_duplicate_location(
    lat: float,
    lng: float,
    accepted: Sequence[Mapping[str, Any]],
    threshold_m: float = DUPLICATE_DISTANCE_THRESHOLD_METERS,
) -> Mapping[str, Any] | None:
    for place in accepted:
        coords = _coords(place)
        if coords is None:
            continue
        if haversine_meters(lat, lng, coords[0], coords[1]) <= threshold_m:
            return place
    return None


def is_duplicate_name(
    name: str,
    accepted: Sequence[Mapping[str, Any]],
    threshold: float = NAME_SIMILARITY_THRESHOLD,
) -> Mapping[str, Any] | None:
    for place in accepted:
        existing = str(place.get("name") or "")
        if name_similarity(name, existing) >= threshold:
            return place
    return None


def should_skip_place(
    place_id: str,
    name: str,
    lat: float | None,
    lng: float | None,
    seen_ids: set[str],
    accepted: Sequence[Mapping[str, Any]],
) -> str | None:
    """Return skip reason, or None if the place should be kept."""
    if not place_id:
        return "missing_place_id"
    if place_id in seen_ids:
        return "duplicate_place_id"
    if lat is not None and lng is not None:
        if is_duplicate_location(lat, lng, accepted) is not None:
            return "duplicate_location"
    if name and is_duplicate_name(name, accepted) is not None:
        return "duplicate_name"
    return None
