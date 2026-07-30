from datascrapping.scrapers.places.models import (
    CSV_FIELDS,
    PlaceRow,
    filters_from_extras,
    known_niches,
    load_search_terms,
    run_slug,
)


def test_csv_fields_include_reserved_email():
    assert "email" in CSV_FIELDS
    assert CSV_FIELDS.index("email") == CSV_FIELDS.index("address") + 1


def test_filters_from_extras_defaults():
    filters = filters_from_extras({"city": "Campinas", "state": "sp"})
    assert filters.city == "Campinas"
    assert filters.state == "SP"
    assert filters.niche == "aasi"
    assert filters.skip_geo_check is False
    assert filters.max_quota == 20000


def test_filters_from_extras_custom():
    filters = filters_from_extras(
        {
            "city": " Americana ",
            "state": "sp",
            "niche": "AASI",
            "skip_geo_check": True,
            "max_quota": 500,
        }
    )
    assert filters.city == "Americana"
    assert filters.state == "SP"
    assert filters.niche == "aasi"
    assert filters.skip_geo_check is True
    assert filters.max_quota == 500


def test_filters_require_city_state():
    try:
        filters_from_extras({"state": "SP"})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "city" in str(exc).lower()


def test_filters_invalid_state():
    try:
        filters_from_extras({"city": "X", "state": "SPO"})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "state" in str(exc).lower() or "UF" in str(exc)


def test_run_slug():
    assert run_slug("Campinas", "SP", "aasi") == "campinas_sp_aasi"
    assert run_slug("São Paulo", "SP", "aasi").startswith("s")


def test_place_row_email_always_empty():
    row = PlaceRow(
        place_id="abc",
        name="Loja",
        email="should-be-cleared@example.com",
        phone="123",
    )
    data = row.to_row()
    assert data["email"] == ""
    assert data["place_id"] == "abc"
    assert data["phone"] == "123"
    assert data["collected_at"]
    assert set(data.keys()) == set(CSV_FIELDS)


def test_load_search_terms_aasi():
    terms = load_search_terms("aasi")
    assert len(terms) >= 3
    assert "aparelhos auditivos" in terms


def test_load_search_terms_empty_niche_fails():
    try:
        load_search_terms("orl")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "failed_no_search_terms" in str(exc)


def test_known_niches():
    assert "aasi" in known_niches()
