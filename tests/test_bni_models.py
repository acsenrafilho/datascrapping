import pytest

from datascrapping.core.checkpoint import SeenStore
from datascrapping.scrapers.bni.models import (
    BniFilters,
    BniMember,
    CSV_FIELDS,
    filters_from_extras,
)


def test_filters_require_specialty_only():
    BniFilters(specialty="Hearing", region=None).validate()
    with pytest.raises(ValueError, match="specialty"):
        BniFilters(specialty="", region="SP").validate()


def test_filters_from_extras_ok():
    filters = filters_from_extras(
        {"region": "SP", "specialty": "Hearing Aids", "country": "Brazil"}
    )
    assert filters.region == "SP"
    assert filters.specialty == "Hearing Aids"
    assert filters.country == "Brazil"


def test_filters_from_extras_specialty_only():
    filters = filters_from_extras({"specialty": "Fonoaudiologia"})
    assert filters.specialty == "Fonoaudiologia"
    assert filters.region is None


def test_filters_from_extras_missing_specialty():
    with pytest.raises(ValueError):
        filters_from_extras({"region": "SP"})


def test_member_to_row_has_csv_fields():
    row = BniMember(name="Ada", profile_url="https://x").to_row()
    assert list(row.keys()) == list(CSV_FIELDS)
    assert row["name"] == "Ada"
    assert row["scraped_at"]


def test_seen_store_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.add("https://a")
    store.save()
    again = SeenStore(path)
    assert "https://a" in again
    assert again.size == 1
