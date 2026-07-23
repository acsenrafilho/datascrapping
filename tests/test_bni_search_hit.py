from datascrapping.scrapers.bni.search import member_from_search_hit


def test_member_from_search_hit():
    member = member_from_search_hit(
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company_name": "Analytical Engines",
            "chapter_name": "BNI Test",
            "city": "London",
            "state": "ENG",
            "country": "United Kingdom",
            "category": "Health & Wellness",
            "speciality": "Hearing/Audiology",
            "user_id": 42,
            "profile_url": (
                "https://www.bniconnectglobal.com/web/secure/networkHome"
                "?userId=42"
            ),
        }
    )
    assert member.name == "Ada Lovelace"
    assert member.company == "Analytical Engines"
    assert member.city == "London, ENG"
    assert member.specialty == "Health & Wellness > Hearing/Audiology"
    assert "userId=42" in member.profile_url


def test_member_from_search_hit_builds_profile_url():
    member = member_from_search_hit(
        {
            "first_name": "Ada",
            "last_name": "",
            "user_id": 99,
        }
    )
    assert member.name == "Ada"
    assert member.profile_url.endswith("userId=99")
