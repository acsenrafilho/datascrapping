from datascrapping.scrapers.bni.categories import (
    BniCategory,
    find_category_matches,
    resolve_specialty,
)


def _cat(
    secondary_id: int,
    primary: str,
    secondary: str,
    *,
    locale: str = "en",
) -> BniCategory:
    return BniCategory(
        primary_id=1,
        secondary_id=secondary_id,
        primary=primary,
        secondary=secondary,
        description=f"{primary} - {secondary}",
        locale=locale,
    )


def test_resolve_specialty_english_exact():
    catalog = {
        "en": [
            _cat(860830, "Health & Wellness", "Hearing/Audiology"),
            _cat(1, "Retail", "Hearing Aids Store"),
        ]
    }
    resolved = resolve_specialty("Hearing/Audiology", catalog)
    assert resolved.secondary == "Hearing/Audiology"
    assert resolved.secondary_id == 860830


def test_resolve_specialty_portuguese_to_english_ui():
    catalog = {
        "en": [_cat(860830, "Health & Wellness", "Hearing/Audiology")],
        "pt_BR": [
            _cat(860830, "Saúde & Bem-estar", "Fonoaudiologia", locale="pt_BR")
        ],
    }
    resolved = resolve_specialty("Fonoaudiologia", catalog)
    assert resolved.locale == "en"
    assert resolved.secondary == "Hearing/Audiology"
    assert resolved.secondary_id == 860830


def test_resolve_specialty_unknown_raises_with_hint():
    catalog = {
        "en": [_cat(860830, "Health & Wellness", "Hearing/Audiology")],
    }
    try:
        resolve_specialty("Completely Unknown Thing", catalog)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not in the Search Category list" in str(exc)
        assert "bni-specialties" in str(exc)


def test_find_category_matches_substring():
    categories = [
        _cat(860830, "Health & Wellness", "Hearing/Audiology"),
        _cat(2, "Legal & Accounting", "Auditor"),
    ]
    matches = find_category_matches("audiolog", categories)
    assert [m.secondary for m in matches] == ["Hearing/Audiology"]
