import os
import uuid

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://api:8000")
S = uuid.uuid4().hex[:8]
BAR = {"id": f"teste-bar-ev-{S}", "name": "Bar do Show", "location": [-35.2071, -5.8695], "address": {"addressLocality": "Natal"},
       "capacity": 60, "occupancy": 0}
REST = {"id": f"teste-rest-ev-{S}", "name": "Restaurante", "location": [-35.21, -5.87], "address": {"addressLocality": "Natal"},
        "capacity": 50, "occupancy": 0}
BASE = {"location": [-35.2071, -5.8695], "address": {"addressLocality": "Natal"}, "eventStatus": ["scheduled"]}
EVENTS = [
    {**BASE, "id": f"teste-oficina-{S}", "name": "Oficina comunitária", "startDate": "2026-12-19T13:00:00Z", "endDate": "2026-12-19T15:00:00Z",
     "category": ["outdoorActivities"], "eventScale": "small", "isAccessibleForFree": True, "audience": ["allPublic"],
     "location": [-35.25, -5.80]},
    {**BASE, "id": f"teste-show-{S}", "name": "Show no bar", "startDate": "2026-12-20T22:00:00Z", "endDate": "2026-12-21T00:30:00Z",
     "category": ["spectacle"], "eventScale": "small", "isAccessibleForFree": False, "audience": ["adult"],
     "refPointOfInterest": {"bar": BAR["id"]}, "venueName": "Bar do Show"},
    {**BASE, "id": f"teste-festival-{S}", "name": "Festival", "startDate": "2027-01-15T18:00:00Z", "endDate": "2027-01-17T04:00:00Z",
     "category": ["spectacle", "gastronomy"], "eventScale": "large", "isAccessibleForFree": True, "location": [-35.2301, -5.8402]},
]
IDS = [e["id"] for e in EVENTS]


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=API_URL, timeout=20) as client:
        yield client


@pytest.fixture(scope="module")
def events(api):
    assert api.post("/v1/bars", json=BAR).status_code == 201
    assert api.post("/v1/restaurants", json=REST).status_code == 201
    for e in EVENTS:
        r = api.post("/v1/events", json=e)
        assert r.status_code == 201, r.text
    yield IDS
    for i in IDS:
        api.delete(f"/v1/events/{i}")
    api.delete(f"/v1/bars/{BAR['id']}")
    api.delete(f"/v1/restaurants/{REST['id']}")


def ours(api, **params) -> list[str]:
    return [e["id"] for e in api.get("/v1/events", params={"limit": 1000, **params}).json() if e["id"] in IDS]


def errors(r: httpx.Response) -> str:
    return " | ".join(r.json()["errors"])


def test_short_place_becomes_urn(api, events):
    body = api.get(f"/v1/events/{IDS[1]}").json()
    assert body["refPointOfInterest"] == f"urn:ngsi-ld:PointOfInterest:{BAR['id']}"
    assert body["startDate"] == "2026-12-20T22:00:00Z"
    assert body["dataOwner"] == "dev-owner"


def test_window_uses_overlap(api, events):
    assert ours(api, **{"from": "2026-12-20", "to": "2026-12-21"}) == [IDS[1]]
    assert ours(api, **{"from": "2027-01-16", "to": "2027-01-17"}) == [IDS[2]]
    assert ours(api, **{"from": "2026-12-21T00:00:00Z", "to": "2026-12-21T01:00:00Z"}) == [IDS[1]]
    assert ours(api, **{"from": "2026-12-21T01:00:00Z", "to": "2026-12-22"}) == []


def test_agenda_is_ordered_by_start(api, events):
    assert ours(api, **{"from": "2026-12-01", "to": "2027-02-01"}) == IDS


def test_filters(api, events):
    assert ours(api, eventScale="large") == [IDS[2]]
    assert ours(api, isAccessibleForFree="true") == [IDS[0], IDS[2]]
    assert ours(api, category="gastronomy") == [IDS[2]]
    assert ours(api, audience="adult") == [IDS[1]]
    assert ours(api, near="-35.2071,-5.8695", maxDistance=500) == [IDS[1]]


@pytest.mark.parametrize("change,reason", [
    ({"endDate": "2026-12-20T21:00:00Z"}, "endDate deve ser posterior a startDate"),
    ({"eventScale": None}, "eventScale"),
    ({"category": ["bathingRestriction"]}, "bathing-restrictions"),
    ({"refPointOfInterest": {"bar": REST["id"]}}, "não encontrado"),
    ({"refPointOfInterest": {"beach": "nao-existe"}}, "não encontrado"),
    ({"refPointOfInterest": {"hotel": "x"}}, "use um destes campos"),
    ({"startDate": "2026-12-20T22:00:00.5Z"}, "startDate"),
])
def test_invalid_event_is_rejected(api, events, change, reason):
    body = {k: v for k, v in {**EVENTS[1], "id": f"{IDS[1]}-x", **change}.items() if v is not None}
    r = api.post("/v1/events", json=body)
    assert r.status_code == 400
    assert reason in errors(r)


def test_invalid_window_is_rejected(api):
    assert api.get("/v1/events", params={"from": "2026-12-21", "to": "2026-12-20"}).status_code == 400
    assert api.get("/v1/events", params={"from": "20/12/2026"}).status_code == 400


def test_update_event(api, events):
    r = api.patch(f"/v1/events/{IDS[1]}", json={"eventStatus": ["cancelled"], "refPointOfInterest": {"restaurant": REST["id"]}})
    assert r.status_code == 200
    body = r.json()
    assert body["eventStatus"] == ["cancelled"]
    assert body["refPointOfInterest"] == f"urn:ngsi-ld:PointOfInterest:{REST['id']}"
    assert api.patch(f"/v1/events/{IDS[1]}", json={"category": ["bathingRestriction"]}).status_code == 400
    assert api.patch(f"/v1/events/{IDS[1]}", json={"endDate": "2026-12-01T00:00:00Z"}).status_code == 400


def test_place_with_events_cannot_be_removed(api, events):
    assert api.patch(f"/v1/events/{IDS[1]}", json={"refPointOfInterest": {"bar": BAR["id"]}}).status_code == 200
    r = api.delete(f"/v1/bars/{BAR['id']}")
    assert r.status_code == 409
    assert "Event.refPointOfInterest" in errors(r)
