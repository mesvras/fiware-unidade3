import re
from dataclasses import replace
from datetime import date

import pytest

from sim import beaches, geo
from sim.config import Config

CFG = Config(api_url="http://api", seed="teste", start_date=date(2026, 11, 14), concurrency=1, interval=1, hotels=12, nights=60)
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
BEACH_TYPES = {"whiteSand", "urban", "isolated", "calmWaters", "blueFlag", "Q-Quality", "strongWaves", "windy", "blackSand"}
FACILITIES = {"promenade", "showers", "cleaningServices", "lifeGuard", "sunshadeRental", "sunLoungerRental", "waterCraftRental",
              "toilets", "touristOffice", "litterBins", "telephone", "surfPracticeArea", "accessforDisabled"}
ACCESS = {"privateVehicle", "boat", "onFoot", "publicTransport"}
REAL_BEACHES = ("Ponta Negra", "Areia Preta", "Meio", "Artistas", "Forte", "Redinha", "Miami", "Via Costeira")


@pytest.fixture(scope="module")
def plan():
    return beaches.generate(CFG)


def test_volume(plan):
    assert len(plan.stations) == 2 and len(plan.beaches) == 6
    assert all(len(b.points) == 2 for b in plan.beaches)


def test_same_seed_gives_same_data(plan):
    again = beaches.generate(CFG)
    assert plan.stations == again.stations and [(b.body, b.points) for b in plan.beaches] == [(b.body, b.points) for b in again.beaches]
    other = beaches.generate(replace(CFG, seed="outra"))
    assert [b.body for b in plan.beaches] != [b.body for b in other.beaches]


def test_ids_are_unique_short_and_prefixed(plan):
    ids = [s["id"] for s in plan.stations] + [b.id for b in plan.beaches] + [p["id"] for b in plan.beaches for p in b.points]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith(beaches.PREFIX) and SHORT_ID.match(i) for i in ids)


def test_beaches_follow_model_rules(plan):
    for b in plan.beaches:
        body = b.body
        assert body["beachType"] and set(body["beachType"]) <= BEACH_TYPES
        assert body["facilities"] and set(body["facilities"]) <= FACILITIES
        assert body["accessType"] and set(body["accessType"]) <= ACCESS
        assert body["occupationRate"] in {"high", "medium", "low", "none"}
        assert body["length"] > 0 and body["width"] > 0


def test_beach_names_are_fictitious(plan):
    assert not any(real in b.body["name"] for b in plan.beaches for real in REAL_BEACHES)


def test_beaches_are_on_coastal_zones(plan):
    for i, b in enumerate(plan.beaches):
        zone = beaches.COASTAL[i % len(beaches.COASTAL)]
        assert zone.coastal and geo.distance_m(b.body["location"], zone.center) <= zone.radius + 1


def test_each_beach_uses_the_nearest_station(plan):
    for b in plan.beaches:
        distances = {s["id"]: geo.distance_m(b.body["location"], s["location"]) for s in plan.stations}
        assert b.body["refWeatherStation"] == min(distances, key=distances.get)


def test_every_station_has_a_beach(plan):
    assert {b.body["refWeatherStation"] for b in plan.beaches} == {s["id"] for s in plan.stations}


def test_points_stay_near_their_beach(plan):
    for b in plan.beaches:
        for p in b.points:
            assert p["refBeach"] == b.id
            assert geo.distance_m(p["location"], b.body["location"]) <= beaches.POINT_RADIUS + 1


def test_stations_are_not_restaurant_fields(plan):
    blocked = {"category", "capacity", "occupancy", "cuisine", "priceRange", "openingHoursSpecification", "refBeach"}
    assert all(not (set(s) & blocked) for s in plan.stations)
