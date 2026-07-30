from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places"

TEXT_SEARCH_QUOTA_COST = 32
PLACE_DETAILS_QUOTA_COST = 17
HTTP_TIMEOUT = 10
PAGE_TOKEN_SLEEP_SECONDS = 2

TEXT_SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount,"
    "places.businessStatus,places.types,places.photos,"
    "places.currentOpeningHours,places.nationalPhoneNumber,"
    "places.internationalPhoneNumber,places.websiteUri,"
    "places.googleMapsUri,places.priceLevel,nextPageToken"
)

DETAILS_FIELD_MASK = (
    "id,displayName,formattedAddress,location,rating,"
    "userRatingCount,nationalPhoneNumber,internationalPhoneNumber,"
    "websiteUri,googleMapsUri,currentOpeningHours,regularOpeningHours,"
    "businessStatus,types,photos,reviews,priceLevel"
)


def build_text_query(term: str, city: str, state: str) -> str:
    return f"{term} em {city}, {state}, Brasil"


def place_to_fields(place: dict[str, Any]) -> dict[str, Any]:
    """Map Places API (New) place object to flat CSV-oriented fields."""
    name = ""
    display = place.get("displayName")
    if isinstance(display, dict):
        name = str(display.get("text") or "")
    elif display:
        name = str(display)

    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")

    types = place.get("types") or []
    types_str = "|".join(str(t) for t in types) if isinstance(types, list) else str(types)

    return {
        "place_id": str(place.get("id") or ""),
        "name": name,
        "address": str(place.get("formattedAddress") or ""),
        "phone": str(place.get("nationalPhoneNumber") or ""),
        "phone_intl": str(place.get("internationalPhoneNumber") or ""),
        "website": str(place.get("websiteUri") or ""),
        "maps_url": str(place.get("googleMapsUri") or ""),
        "lat": "" if lat is None else str(lat),
        "lng": "" if lng is None else str(lng),
        "rating": "" if place.get("rating") is None else str(place.get("rating")),
        "user_ratings_total": (
            ""
            if place.get("userRatingCount") is None
            else str(place.get("userRatingCount"))
        ),
        "business_status": str(place.get("businessStatus") or ""),
        "types": types_str,
    }


def merge_place_fields(
    text_fields: dict[str, Any],
    details_fields: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(text_fields)
    if details_fields:
        for key, value in details_fields.items():
            if value not in (None, ""):
                merged[key] = value
    return merged


class PlacesClient:
    """Thin Google Places API (New) client for Text Search + Details."""

    def __init__(
        self,
        api_key: str,
        *,
        http_post: Callable[..., Any] | None = None,
        http_get: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self._post = http_post or requests.post
        self._get = http_get or requests.get
        self._sleep = sleep

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def search_text_pages(
        self,
        term: str,
        city: str,
        state: str,
    ) -> list[tuple[list[dict[str, Any]], int]]:
        """Yield-like list of (places_as_fields, page_quota_cost) per page.

        Caller owns quota accounting and early stop. Sleeps 2s before pageToken.
        """
        pages: list[tuple[list[dict[str, Any]], int]] = []
        next_page_token: str | None = None
        full_query = build_text_query(term, city, state)
        logger.info("Text search: %s", full_query)

        while True:
            body: dict[str, Any] = {
                "textQuery": full_query,
                "languageCode": "pt-BR",
            }
            if next_page_token:
                body["pageToken"] = next_page_token
                self._sleep(PAGE_TOKEN_SLEEP_SECONDS)

            response = self._post(
                PLACES_TEXT_SEARCH_URL,
                json=body,
                headers=self._headers(TEXT_SEARCH_FIELD_MASK),
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            raw_places = data.get("places") or []
            fields = [place_to_fields(p) for p in raw_places]
            pages.append((fields, TEXT_SEARCH_QUOTA_COST))

            next_page_token = data.get("nextPageToken")
            if not next_page_token or not raw_places:
                break

        return pages

    def get_details(self, place_id: str) -> dict[str, Any] | None:
        if not place_id:
            return None
        # New API resource name: places/{PLACE_ID}
        url = f"{PLACES_DETAILS_URL}/{place_id}"
        try:
            response = self._get(
                url,
                headers=self._headers(DETAILS_FIELD_MASK),
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            return place_to_fields(response.json())
        except requests.exceptions.RequestException as exc:
            logger.error("Details failed for %s: %s", place_id, exc)
            return None
