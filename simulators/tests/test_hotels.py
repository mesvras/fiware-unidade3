import re
from dataclasses import replace
from datetime import date

import pytest

from sim import hotels
from sim.config import Config

CFG = Config(api_url="http://api", seed="teste", start_date=date(2026, 11, 14), concurrency=1, interval=1, hotels=12, nights=60)
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
AMENITIES = {"wifi", "pool", "parking", "breakfast", "airConditioning", "beachfront", "accessible"}


@pytest.fixture(scope="module")
def plans():
    return hotels.generate(CFG)


def all_nights(plans, cfg=CFG):
    return [(h, r, hotels.generate_night(cfg.seed, h, r, d, cfg.start_date))
            for h in plans for r in h.rooms for d in hotels.days(cfg.start_date, cfg.nights)]


def test_same_seed_gives_same_data(plans):
    again = hotels.generate(CFG)
    assert [h.body for h in plans] == [h.body for h in again]
    assert [n for *_, n in all_nights(plans)] == [n for *_, n in all_nights(again)]


def test_other_seed_gives_other_data(plans):
    assert [h.body for h in plans] != [h.body for h in hotels.generate(replace(CFG, seed="outra"))]


def test_volume_does_not_change_existing_hotels(plans):
    fewer = hotels.generate(replace(CFG, hotels=5))
    assert [h.body for h in fewer] == [h.body for h in plans[:5]]


def test_ids_are_unique_short_and_prefixed(plans):
    ids = [h.id for h in plans]
    assert len(set(ids)) == len(ids)
    for h in plans:
        assert h.id.startswith(hotels.PREFIX) and SHORT_ID.match(h.id)
        assert all(SHORT_ID.match(r.body["id"]) for r in h.rooms)


def test_hotels_follow_model_rules(plans):
    for h in plans:
        b = h.body
        low, high = hotels.CATEGORIES[b["category"]][1]
        assert low <= b["starRating"] <= high
        assert set(b["amenities"]) <= AMENITIES
        assert re.fullmatch(r"\d\d:\d\d", b["checkInTime"]) and re.fullmatch(r"\d\d:\d\d", b["checkOutTime"])
        assert b["name"].startswith(hotels.CATEGORIES[b["category"]][0] + " ")
        assert 2 <= len(h.rooms) <= 4


def test_coastal_hotels_are_beachfront(plans):
    for i, h in enumerate(plans):
        zone = hotels.geo.ZONES[i % len(hotels.geo.ZONES)]
        assert ("beachfront" in h.body["amenities"]) == zone.coastal


def test_all_zones_have_hotels(plans):
    zones = {h.body["address"]["streetAddress"].rsplit(", ", 1)[1] for h in plans}
    assert zones == {z.name for z in hotels.geo.ZONES}


def test_room_types_follow_model_rules(plans):
    for h in plans:
        for r in h.rooms:
            assert r.body["maxAdults"] >= 1 and r.body["maxChildren"] >= 0 and r.body["totalUnits"] >= 1


def test_nights_follow_model_rules(plans):
    for h, r, n in all_nights(plans):
        assert 0 <= n["availableUnits"] <= r.body["totalUnits"]
        assert n["pricePerNight"]["value"] > 0 and n["pricePerNight"]["currency"] == "BRL"
        assert n.get("minimumStay", 1) >= 1
        date.fromisoformat(n["stayDate"])


def test_high_season_and_weekend_cost_more(plans):
    h, r = plans[0], plans[0].rooms[0]
    weekday_low, weekend_low = date(2026, 11, 18), date(2026, 11, 20)
    weekday_high = date(2027, 1, 13)
    assert hotels.night_price(h, r, weekend_low) > hotels.night_price(h, r, weekday_low)
    assert hotels.night_price(h, r, weekday_high) > hotels.night_price(h, r, weekday_low)


def test_minimum_stay_on_peak_nights():
    assert hotels.minimum_stay(date(2026, 12, 30)) == 3
    assert hotels.minimum_stay(date(2027, 1, 1)) == 3
    assert hotels.minimum_stay(date(2027, 1, 8)) == 2
    assert hotels.minimum_stay(date(2026, 11, 20)) is None


def test_occupancy_grows_near_date_and_in_high_season(plans):
    today = date(2026, 11, 14)
    nights = all_nights(plans, replace(CFG, nights=60))

    def rate(selector):
        chosen = [(r.body["totalUnits"] - n["availableUnits"]) / r.body["totalUnits"] for _, r, n in nights if selector(date.fromisoformat(n["stayDate"]))]
        return sum(chosen) / len(chosen)

    near = rate(lambda d: (d - today).days < 7 and d.month == 11)
    far = rate(lambda d: (d - today).days >= 14 and d.month == 11)
    high = rate(lambda d: d.month == 12 and (d - today).days >= 14)
    assert near > far and high > far


def test_scenario_start_avoids_long_minimum_stay():
    cfg = replace(CFG, start_date=date(2026, 12, 20))
    start = hotels.scenario_start(cfg, 3, 2)
    assert all((hotels.minimum_stay(d) or 1) <= 2 for d in hotels.days(start, 2))
