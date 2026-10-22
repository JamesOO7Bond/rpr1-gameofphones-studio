from app.regions import DEFAULT_REGIONS, normalize_region
from app.rotation import next_region


def test_first_pick_is_land_allgemein():
    assert next_region(DEFAULT_REGIONS, []) == "Land allgemein"


def test_last_two_regions_are_blocked():
    history = ["Land allgemein", "Pfalz"]
    pick = next_region(DEFAULT_REGIONS, history)
    assert pick not in history


def test_rotation_covers_all_regions_within_twenty_rounds():
    history: list[str] = []
    for _ in range(20):
        history.insert(0, next_region(DEFAULT_REGIONS, history))
    assert set(history) == {r["name"] for r in DEFAULT_REGIONS}


def test_land_allgemein_comes_more_often_than_hochwald():
    history: list[str] = []
    for _ in range(60):
        history.insert(0, next_region(DEFAULT_REGIONS, history))
    assert history.count("Land allgemein") > history.count("Hochwald")
    assert history.count("Land allgemein") >= history.count("Pfalz")


def test_normalize_region():
    assert normalize_region("Pfälzerwald") == "Pfalz"
    assert normalize_region("Hunsrueck") == "Hunsrück"
    assert normalize_region("Rheinland-Pfalz allgemein") == "Land allgemein"
    assert normalize_region("") is None
    assert normalize_region("Bayern") is None
