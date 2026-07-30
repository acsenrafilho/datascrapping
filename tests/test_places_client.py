import json
from pathlib import Path
from unittest.mock import MagicMock

from datascrapping.scrapers.places.client import (
    DETAILS_FIELD_MASK,
    PLACE_DETAILS_QUOTA_COST,
    TEXT_SEARCH_FIELD_MASK,
    TEXT_SEARCH_QUOTA_COST,
    PlacesClient,
    build_text_query,
    merge_place_fields,
    place_to_fields,
)

FIXTURES = Path(__file__).parent / "fixtures" / "places"


def test_build_text_query():
    assert (
        build_text_query("aparelhos auditivos", "Campinas", "SP")
        == "aparelhos auditivos em Campinas, SP, Brasil"
    )


def test_field_masks_stable():
    assert "places.id" in TEXT_SEARCH_FIELD_MASK
    assert "nextPageToken" in TEXT_SEARCH_FIELD_MASK
    assert DETAILS_FIELD_MASK.startswith("id,")
    assert "nationalPhoneNumber" in DETAILS_FIELD_MASK


def test_place_to_fields_from_fixture():
    payload = json.loads((FIXTURES / "text_search_page.json").read_text())
    place = payload["places"][0]
    fields = place_to_fields(place)
    assert fields["place_id"] == "ChIJtest123"
    assert fields["name"] == "Auditiva Campinas"
    assert fields["phone"] == "(19) 3000-0000"
    assert fields["phone_intl"] == "+55 19 3000-0000"
    assert fields["address"].startswith("Rua Exemplo")
    assert fields["website"] == "https://example.com"
    assert fields["maps_url"].startswith("https://maps.google.com")
    assert fields["lat"] == "-22.9056"
    assert fields["lng"] == "-47.0608"
    assert "store" in fields["types"]
    assert "|" in fields["types"]


def test_merge_prefers_details_nonempty():
    text = place_to_fields(
        json.loads((FIXTURES / "text_search_page.json").read_text())["places"][0]
    )
    details = place_to_fields(
        json.loads((FIXTURES / "details.json").read_text())
    )
    merged = merge_place_fields(text, details)
    assert merged["rating"] == "4.6"
    assert "health" in merged["types"]


def test_search_text_pages_mocked():
    payload = json.loads((FIXTURES / "text_search_page.json").read_text())
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    slept: list[float] = []

    client = PlacesClient(
        "fake-key",
        http_post=lambda *a, **k: resp,
        sleep=slept.append,
    )
    pages = client.search_text_pages("aparelhos auditivos", "Campinas", "SP")
    assert len(pages) == 1
    places, cost = pages[0]
    assert cost == TEXT_SEARCH_QUOTA_COST
    assert places[0]["place_id"] == "ChIJtest123"
    assert slept == []


def test_get_details_mocked():
    payload = json.loads((FIXTURES / "details.json").read_text())
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload

    client = PlacesClient("fake-key", http_get=lambda *a, **k: resp)
    details = client.get_details("ChIJtest123")
    assert details is not None
    assert details["name"] == "Auditiva Campinas"
    assert PLACE_DETAILS_QUOTA_COST == 17
