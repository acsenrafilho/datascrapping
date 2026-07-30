from datascrapping.scrapers.places.dedupe import (
    DUPLICATE_DISTANCE_THRESHOLD_METERS,
    haversine_meters,
    name_similarity,
    should_skip_place,
)


def test_haversine_same_point():
    assert haversine_meters(-22.9, -47.0, -22.9, -47.0) == 0.0


def test_haversine_under_and_over_threshold():
    # ~37 m north of origin-ish offset at this latitude
    base_lat, base_lng = -22.9056, -47.0608
    near_lat = base_lat + 0.0003  # ~33 m
    far_lat = base_lat + 0.0006  # ~67 m
    near = haversine_meters(base_lat, base_lng, near_lat, base_lng)
    far = haversine_meters(base_lat, base_lng, far_lat, base_lng)
    assert near < DUPLICATE_DISTANCE_THRESHOLD_METERS
    assert far > DUPLICATE_DISTANCE_THRESHOLD_METERS


def test_name_similarity_threshold():
    assert name_similarity("Auditiva Campinas", "Auditiva Campinas") == 1.0
    assert name_similarity("Auditiva Campinas", "auditiva campinas") == 1.0
    assert name_similarity("A", "Z") < 0.90


def test_should_skip_duplicate_place_id():
    reason = should_skip_place(
        "id1",
        "Loja",
        -22.9,
        -47.0,
        {"id1"},
        [],
    )
    assert reason == "duplicate_place_id"


def test_should_skip_duplicate_location():
    accepted = [{"place_id": "other", "name": "X", "lat": "-22.9056", "lng": "-47.0608"}]
    reason = should_skip_place(
        "new",
        "Y",
        -22.9056,
        -47.0608,
        set(),
        accepted,
    )
    assert reason == "duplicate_location"


def test_should_skip_duplicate_name():
    accepted = [
        {"place_id": "other", "name": "Centro Auditivo ABC", "lat": "-23.0", "lng": "-46.0"}
    ]
    reason = should_skip_place(
        "new",
        "Centro Auditivo ABC",
        -22.0,
        -47.0,
        set(),
        accepted,
    )
    assert reason == "duplicate_name"


def test_should_keep_distinct_place():
    accepted = [
        {"place_id": "other", "name": "Outra Loja", "lat": "-23.5", "lng": "-46.5"}
    ]
    reason = should_skip_place(
        "new",
        "Loja Distinta",
        -22.9,
        -47.0,
        set(),
        accepted,
    )
    assert reason is None
