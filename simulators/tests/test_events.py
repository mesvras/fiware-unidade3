import re
from dataclasses import replace
from datetime import date, datetime

import pytest

from sim import events, venues
from sim.config import Config

CFG = Config(api_url="http://api", seed="teste", start_date=date(2026, 11, 14), concurrency=1, interval=1, hotels=12, nights=60)
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
UTC_TEXT = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
CATEGORIES = {"excursion", "gastronomy", "history", "museum", "outdoorActivities", "parksAndGardens", "religiousWorship",
              "shopping", "spectacle", "wellness", "conference"}
STATUS = {"scheduled", "opened", "closed", "suspended", "cancelled", "finished", "postponed", "rescheduled"}
AUDIENCE = {"adult", "allPublic", "children", "family", "senior", "teenager"}


def local(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(venues.LOCAL)


@pytest.fixture(scope="module")
def plans():
    return events.generate(CFG)


def test_volume_and_mix(plans):
    assert len(plans) == 40
    assert {k: sum(e.kind == k for e in plans) for k in ("show", "workshop", "festival", "conference")} == \
        {"show": 18, "workshop": 10, "festival": 6, "conference": 6}


def test_same_seed_gives_same_data(plans):
    assert [e.body for e in plans] == [e.body for e in events.generate(CFG)]
    assert [e.body for e in plans] != [e.body for e in events.generate(replace(CFG, seed="outra"))]


def test_ids_are_unique_short_and_prefixed(plans):
    ids = [e.id for e in plans]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith(events.PREFIX) and SHORT_ID.match(i) for i in ids)


def test_events_follow_model_rules(plans):
    for e in plans:
        b = e.body
        assert UTC_TEXT.match(b["startDate"]) and UTC_TEXT.match(b["endDate"]) and b["endDate"] > b["startDate"]
        assert b["eventScale"] in {"small", "medium", "large"}
        assert b["category"] and set(b["category"]) <= CATEGORIES
        assert len(b["eventStatus"]) == 1 and set(b["eventStatus"]) <= STATUS
        assert set(b["audience"]) <= AUDIENCE
        assert b["maximumAttendeeCapacity"] >= 1
        for price in ("eventPriceFrom", "eventPriceTo"):
            if price in b:
                assert b[price]["currency"] == "BRL" and b[price]["value"] >= 0
        if "eventPriceTo" in b:
            assert b["eventPriceTo"]["value"] >= b["eventPriceFrom"]["value"]
        assert b["address"]["addressLocality"] == "Natal"


def test_events_fall_inside_the_period(plans):
    first = CFG.start_date
    last = date.fromordinal(first.toordinal() + CFG.event_days)
    for e in plans:
        assert first <= local(e.start).date() and local(e.end).date() <= last


def test_shows_happen_in_bars_from_thursday_to_sunday(plans):
    bars = {v.id: v for v in venues.generate(CFG) if v.kind == "bar"}
    for e in plans:
        if e.kind != "show":
            continue
        bar = bars[e.body["refPointOfInterest"]["bar"]]
        assert local(e.start).weekday() in (3, 4, 5, 6)
        assert e.body["maximumAttendeeCapacity"] <= bar.body["capacity"]
        assert e.body["location"] == bar.body["location"] and e.body["address"] == bar.body["address"]


def test_conferences_use_the_new_category(plans):
    assert all(e.body["category"] == ["conference"] for e in plans if e.kind == "conference")


def test_some_events_are_not_scheduled(plans):
    status = [e.body["eventStatus"][0] for e in plans]
    assert status.count("cancelled") == 2 and status.count("postponed") == 1


def test_overlap_uses_the_whole_event():
    event = events.Event({"id": "x", "startDate": "2026-11-20T23:00:00Z", "endDate": "2026-11-21T02:30:00Z"}, "show")
    assert events.overlaps(event, date(2026, 11, 21), date(2026, 11, 22))
    assert events.overlaps(event, date(2026, 11, 20), date(2026, 11, 21))
    assert not events.overlaps(event, date(2026, 11, 22), date(2026, 11, 23))


def test_windows_stay_inside_the_period():
    for _, first, last in events.windows(CFG):
        assert CFG.start_date <= first < last <= date.fromordinal(CFG.start_date.toordinal() + CFG.event_days)
