import os
import uuid

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://api:8000")
S = uuid.uuid4().hex[:8]
STATION = {"id": f"teste-estacao-{S}", "name": "Estação Teste", "location": [-35.2000, -5.7800]}
BEACH = {"id": f"teste-praia-{S}", "name": "Praia Teste", "location": [-35.1990, -5.7790], "refWeatherStation": STATION["id"],
         "beachType": ["urban", "calmWaters"], "facilities": ["showers", "lifeGuard"], "occupationRate": "medium"}
POINT = {"id": f"teste-coleta-{S}", "name": "Coleta Teste", "location": [-35.1992, -5.7793], "refBeach": BEACH["id"]}
REST = {"id": f"teste-rest-pr-{S}", "name": "Restaurante", "location": [-35.21, -5.87], "address": {"addressLocality": "Natal"},
        "capacity": 50, "occupancy": 0}
EVENT = {"id": f"teste-evento-pr-{S}", "name": "Mutirão na praia", "startDate": "2026-12-27T12:00:00Z", "endDate": "2026-12-27T15:00:00Z",
         "location": [-35.1990, -5.7790], "address": {"addressLocality": "Natal"}, "category": ["outdoorActivities"],
         "eventScale": "medium", "eventStatus": ["scheduled"], "refPointOfInterest": {"beach": BEACH["id"]}}


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=API_URL, timeout=20) as client:
        yield client


@pytest.fixture(scope="module")
def place(api):
    assert api.post("/v1/weather-stations", json=STATION).status_code == 201
    assert api.post("/v1/restaurants", json=REST).status_code == 201
    assert api.post("/v1/beaches", json=BEACH).status_code == 201
    assert api.post("/v1/sampling-points", json=POINT).status_code == 201
    yield BEACH["id"]
    api.delete(f"/v1/events/{EVENT['id']}")
    api.delete(f"/v1/sampling-points/{POINT['id']}")
    api.delete(f"/v1/beaches/{BEACH['id']}")
    api.delete(f"/v1/weather-stations/{STATION['id']}")
    api.delete(f"/v1/restaurants/{REST['id']}")


def errors(r: httpx.Response) -> str:
    return " | ".join(r.json()["errors"])


def test_beach_links_station_and_point_links_beach(api, place):
    beach = api.get(f"/v1/beaches/{BEACH['id']}").json()
    assert beach["refWeatherStation"] == STATION["id"]
    assert beach["dataOwner"] == "dev-owner"
    point = api.get(f"/v1/sampling-points/{POINT['id']}").json()
    assert point["refBeach"] == BEACH["id"]
    assert point["category"] == ["bathingSamplingPoint"]
    assert api.get(f"/v1/weather-stations/{STATION['id']}").json()["category"] == ["weatherStation"]


def test_category_routes_are_separate(api, place):
    assert api.get(f"/v1/weather-stations/{POINT['id']}").status_code == 404
    assert api.get(f"/v1/sampling-points/{STATION['id']}").status_code == 404
    assert api.get(f"/v1/restaurants/{STATION['id']}").status_code == 404


def test_filters(api, place):
    def ids(path, **params):
        return [x["id"] for x in api.get(path, params=params).json()]

    assert BEACH["id"] in ids("/v1/beaches", beachType="urban", facilities="lifeGuard", near="-35.199,-5.779", maxDistance=300)
    assert BEACH["id"] not in ids("/v1/beaches", beachType="isolated")
    assert ids("/v1/sampling-points", beach=BEACH["id"]) == [POINT["id"]]
    assert STATION["id"] in ids("/v1/weather-stations", near="-35.2,-5.78", maxDistance=100)


@pytest.mark.parametrize("path,body,reason", [
    ("/v1/beaches", {**BEACH, "id": f"x-{S}", "refWeatherStation": REST["id"]}, "estação meteorológica"),
    ("/v1/beaches", {**BEACH, "id": f"x-{S}", "beachType": ["rochosa"]}, "beachType"),
    ("/v1/sampling-points", {k: v for k, v in POINT.items() if k != "refBeach"} | {"id": f"x-{S}"}, "refBeach"),
    ("/v1/sampling-points", {**POINT, "id": f"x-{S}", "refBeach": "nao-existe"}, "entidade inexistente"),
    ("/v1/sampling-points", {**POINT, "id": f"x-{S}", "occupancy": 3}, "occupancy: não se aplica"),
    ("/v1/weather-stations", {**STATION, "id": f"x-{S}", "refBeach": BEACH["id"]}, "refBeach: não se aplica"),
    ("/v1/weather-stations", {**STATION, "id": f"x-{S}", "category": ["bar"]}, "category: definido pela API"),
])
def test_invalid_places_are_rejected(api, place, path, body, reason):
    r = api.post(path, json=body)
    assert r.status_code == 400
    assert reason in errors(r)


def test_event_can_point_to_beach(api, place):
    r = api.post("/v1/events", json=EVENT)
    assert r.status_code == 201, r.text
    assert r.json()["refPointOfInterest"] == f"urn:ngsi-ld:Beach:{BEACH['id']}"


def test_update_beach(api, place):
    assert api.patch(f"/v1/beaches/{BEACH['id']}", json={"occupationRate": "high"}).json()["occupationRate"] == "high"
    assert api.patch(f"/v1/beaches/{BEACH['id']}", json={"refWeatherStation": REST["id"]}).status_code == 400


def test_delete_is_blocked_while_referenced(api, place):
    assert api.delete(f"/v1/weather-stations/{STATION['id']}").status_code == 409
    r = api.delete(f"/v1/beaches/{BEACH['id']}")
    assert r.status_code == 409
    assert "PointOfInterest.refBeach" in errors(r)
    assert api.delete(f"/v1/sampling-points/{POINT['id']}").status_code == 204
    r = api.delete(f"/v1/beaches/{BEACH['id']}")
    assert r.status_code == 409
    assert "Event.refPointOfInterest" in errors(r)
