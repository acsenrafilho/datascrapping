from datascrapping.core.checkpoint import SeenStore
from datascrapping.scrapers.bni.models import (
    BniFilters,
    BniMember,
    CSV_FIELDS,
    filters_from_extras,
)


def test_filters_allow_optional_specialty():
    BniFilters(specialty="Hearing", region=None).validate()
    BniFilters(specialty=None, region="SP").validate()
    BniFilters().validate()


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


def test_filters_from_extras_without_specialty():
    filters = filters_from_extras({"region": "SP"})
    assert filters.specialty is None
    assert filters.region == "SP"


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
