import random
import re
from dataclasses import replace
from datetime import date, datetime

import pytest

from sim import geo, venues
from sim.config import Config

CFG = Config(api_url="http://api", seed="teste", start_date=date(2026, 11, 14), concurrency=1, interval=1, hotels=12, nights=60)
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=venues.LOCAL)


@pytest.fixture(scope="module")
def plans():
    return venues.generate(CFG)


def test_volume_and_kinds(plans):
    assert sum(v.kind == "restaurant" for v in plans) == 25
    assert sum(v.kind == "bar" for v in plans) == 15


def test_same_seed_gives_same_data(plans):
    assert [v.body for v in plans] == [v.body for v in venues.generate(CFG)]
    assert [v.body for v in plans] != [v.body for v in venues.generate(replace(CFG, seed="outra"))]


def test_volume_does_not_change_existing_venues(plans):
    fewer = venues.generate(replace(CFG, restaurants=5, bars=3))
    assert [v.body for v in fewer] == [v.body for v in plans[:5]] + [v.body for v in plans[25:28]]


def test_ids_are_unique_short_and_prefixed(plans):
    ids = [v.id for v in plans]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith(venues.PREFIX) and SHORT_ID.match(i) for i in ids)


def test_venues_follow_model_rules(plans):
    allowed = set(venues.CUISINES) | {venues.BAR_CUISINE}
    for v in plans:
        b = v.body
        assert b["capacity"] >= 1 and 0 <= b["occupancy"] <= b["capacity"]
        assert re.fullmatch(r"\${1,4}", b["priceRange"])
        assert set(b["cuisine"]) <= allowed and all(c == c.lower() for c in b["cuisine"])
        assert "category" not in b and "availabilityLevel" not in b
        for spec in b["openingHoursSpecification"]:
            assert set(spec) == {"dayOfWeek", "opens", "closes"} and set(spec["dayOfWeek"]) <= set(venues.DAYS)


def test_venues_are_in_hotel_zones(plans):
    for i, v in enumerate(plans):
        index = i if v.kind == "restaurant" else i - 25
        zone = geo.ZONES[index % len(geo.ZONES)]
        assert v.body["address"]["postalCode"].startswith(zone.postal_prefix)
        assert geo.distance_m(v.body["location"], zone.center) <= zone.radius + 1


def test_opening_hours_cross_midnight():
    hours = [{"dayOfWeek": ["Friday"], "opens": "17:00", "closes": "02:00"}]
    assert venues.is_open(hours, at(20, 23))
    assert venues.is_open(hours, at(21, 1, 30))
    assert not venues.is_open(hours, at(21, 2, 30))
    assert not venues.is_open(hours, at(20, 16))


def test_restaurant_demand_peaks_at_meals():
    assert venues.demand("restaurant", at(18, 13)) > venues.demand("restaurant", at(18, 16))
    assert venues.demand("restaurant", at(18, 20, 30)) > venues.demand("restaurant", at(18, 17))


def test_bar_demand_peaks_at_night_and_weekend():
    assert venues.demand("bar", at(18, 22)) > venues.demand("bar", at(18, 15))
    assert venues.demand("bar", at(20, 22)) > venues.demand("bar", at(18, 22))


def test_closed_venue_has_no_occupancy(plans):
    bar = next(v for v in plans if v.kind == "bar")
    assert venues.target_occupancy(bar, at(18, 10)) == 0


def test_next_occupancy_stays_in_bounds(plans):
    rng = random.Random(1)
    for v in plans:
        current = 0
        for hour in range(24):
            current = venues.next_occupancy(rng, v, current, at(20, hour))
            assert 0 <= current <= v.body["capacity"]


def test_occupancy_of_accepts_number_and_observed_value():
    assert venues.occupancy_of({"occupancy": 12}) == 12
    assert venues.occupancy_of({"occupancy": {"value": 12, "observedAt": "2026-11-15T01:56:45.619Z"}}) == 12


def test_expected_level():
    assert venues.expected_level(100, 100) == "full"
    assert venues.expected_level(100, 70) == "limited"
    assert venues.expected_level(100, 69) == "available"
