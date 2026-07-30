from datascrapping.scrapers.bni.categories import (
    BniCategory,
    find_category_matches,
    normalize_locale,
    resolve_primary_category,
    resolve_search_filters,
    resolve_specialty,
)


def _cat(
    secondary_id: int,
    primary: str,
    secondary: str,
    *,
    locale: str = "en",
    primary_id: int = 1,
) -> BniCategory:
    return BniCategory(
        primary_id=primary_id,
        secondary_id=secondary_id,
        primary=primary,
        secondary=secondary,
        description=f"{primary} - {secondary}",
        locale=locale,
    )


def test_resolve_specialty_english_exact():
    catalog = {
        "en": [
            _cat(860830, "Health & Wellness", "Hearing/Audiology", primary_id=86),
            _cat(1, "Retail", "Hearing Aids Store", primary_id=2),
        ]
    }
    resolved = resolve_specialty("Hearing/Audiology", catalog)
    assert resolved.secondary == "Hearing/Audiology"
    assert resolved.secondary_id == 860830


def test_resolve_specialty_portuguese_to_english_ui():
    catalog = {
        "en": [
            _cat(
                860830,
                "Health & Wellness",
                "Hearing/Audiology",
                primary_id=86,
            )
        ],
        "pt_BR": [
            _cat(
                860830,
                "Saúde & Bem-estar",
                "Fonoaudiologia",
                locale="pt_BR",
                primary_id=86,
            )
        ],
    }
    resolved = resolve_specialty("Fonoaudiologia", catalog)
    assert resolved.locale == "en"
    assert resolved.secondary == "Hearing/Audiology"
    assert resolved.secondary_id == 860830


def test_resolve_specialty_unknown_raises_with_hint():
    catalog = {
        "en": [
            _cat(
                860830,
                "Health & Wellness",
                "Hearing/Audiology",
                primary_id=86,
            )
        ],
    }
    try:
        resolve_specialty("Completely Unknown Thing", catalog)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not in the Search Category list" in str(exc)
        assert "bni-specialties" in str(exc)


def test_find_category_matches_substring():
    categories = [
        _cat(860830, "Health & Wellness", "Hearing/Audiology", primary_id=86),
        _cat(2, "Legal & Accounting", "Auditor", primary_id=3),
    ]
    matches = find_category_matches("audiolog", categories)
    assert [m.secondary for m in matches] == ["Hearing/Audiology"]


def test_resolve_primary_category_english():
    catalog = {
        "en": [
            _cat(
                860830,
                "Health & Wellness",
                "Hearing/Audiology",
                primary_id=86,
            ),
            _cat(99, "Health & Wellness", "Nutritionist", primary_id=86),
            _cat(1, "Retail", "Hearing Aids Store", primary_id=2),
        ]
    }
    resolved = resolve_primary_category("Health & Wellness", catalog)
    assert resolved.primary_id == 86
    assert resolved.secondary_id == 0
    assert resolved.is_primary_only
    assert resolved.primary == "Health & Wellness"


def test_resolve_primary_category_portuguese_to_english():
    catalog = {
        "en": [
            _cat(
                860830,
                "Health & Wellness",
                "Hearing/Audiology",
                primary_id=86,
            )
        ],
        "pt_BR": [
            _cat(
                860830,
                "Saúde & Bem-estar",
                "Fonoaudiologia",
                locale="pt_BR",
                primary_id=86,
            )
        ],
    }
    resolved = resolve_primary_category("Saúde & Bem-estar", catalog)
    assert resolved.primary_id == 86
    assert resolved.primary == "Health & Wellness"
    assert resolved.is_primary_only


def test_resolve_search_filters_category_only():
    catalog = {
        "en": [
            _cat(
                860830,
                "Health & Wellness",
                "Hearing/Audiology",
                primary_id=86,
            )
        ]
    }
    resolved = resolve_search_filters(
        catalog, specialty=None, category="Health & Wellness"
    )
    assert resolved is not None
    assert resolved.primary_id == 86
    assert resolved.secondary_id == 0


def test_resolve_search_filters_none():
    assert resolve_search_filters({}, specialty=None, category=None) is None


def test_normalize_locale_aliases():
    assert normalize_locale("pt") == "pt_BR"
    assert normalize_locale("pt-BR") == "pt_BR"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("es") == "es"


def test_expand_search_targets_category_to_specialties():
    from datascrapping.scrapers.bni.categories import expand_search_targets

    catalog = {
        "en": [
            _cat(10, "Health & Wellness", "Acupuncture", primary_id=86),
            _cat(11, "Health & Wellness", "Hearing/Audiology", primary_id=86),
            _cat(12, "Retail", "Other", primary_id=2),
        ]
    }
    primary = resolve_primary_category("Health & Wellness", catalog)
    targets = expand_search_targets(primary, catalog)
    assert len(targets) == 2
    assert [t.secondary for t in targets] == [
        "Acupuncture",
        "Hearing/Audiology",
    ]


def test_expand_search_targets_specialty_passthrough():
    from datascrapping.scrapers.bni.categories import expand_search_targets

    catalog = {
        "en": [
            _cat(
                860830,
                "Health & Wellness",
                "Hearing/Audiology",
                primary_id=86,
            )
        ]
    }
    resolved = resolve_specialty("Hearing/Audiology", catalog)
    targets = expand_search_targets(resolved, catalog)
    assert len(targets) == 1
    assert targets[0].secondary_id == 860830
