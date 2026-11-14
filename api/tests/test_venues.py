import os
import uuid
from datetime import datetime

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://api:8000")
SUFFIX = uuid.uuid4().hex[:8]
RID, BID = f"teste-rest-{SUFFIX}", f"teste-bar-{SUFFIX}"
RESTAURANT = {"id": RID, "name": "Restaurante Teste", "location": [-35.2062, -5.8688], "address": {"addressLocality": "Natal"},
              "capacity": 80, "occupancy": 10, "cuisine": ["regional", "frutos do mar"], "priceRange": "$$",
              "openingHoursSpecification": [{"dayOfWeek": ["Friday"], "opens": "11:00", "closes": "23:30"}]}
BAR = {"id": BID, "name": "Bar Teste", "location": [-35.2071, -5.8695], "address": {"addressLocality": "Natal"},
       "capacity": 40, "occupancy": {"value": 30, "observedAt": "2026-12-20T22:00:00Z"}}


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=API_URL, timeout=20) as client:
        yield client


@pytest.fixture(scope="module")
def venues(api):
    assert api.post("/v1/restaurants", json=RESTAURANT).status_code == 201
    assert api.post("/v1/bars", json=BAR).status_code == 201
    yield RID, BID
    api.delete(f"/v1/restaurants/{RID}")
    api.delete(f"/v1/bars/{BID}")


def instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def errors(r: httpx.Response) -> str:
    return " | ".join(r.json()["errors"])


def test_restaurant_gets_category_level_owner_and_observed_at(api, venues):
    body = api.get(f"/v1/restaurants/{RID}").json()
    assert body["category"] == ["restaurant"]
    assert body["availabilityLevel"] == "available"
    assert body["dataOwner"] == "dev-owner"
    assert body["occupancy"]["value"] == 10
    assert body["occupancy"]["observedAt"].endswith("Z")


def test_bar_keeps_given_observed_at_and_is_limited(api, venues):
    body = api.get(f"/v1/bars/{BID}").json()
    assert body["occupancy"]["value"] == 30
    assert instant(body["occupancy"]["observedAt"]) == instant("2026-12-20T22:00:00Z")
    assert body["availabilityLevel"] == "limited"


def test_routes_do_not_mix_categories(api, venues):
    assert api.get(f"/v1/bars/{RID}").status_code == 404
    assert api.get(f"/v1/restaurants/{BID}").status_code == 404
    assert RID not in [b["id"] for b in api.get("/v1/bars").json()]


@pytest.mark.parametrize("change,reason", [
    ({"capacity": None}, "capacity"),
    ({"occupancy": 81}, "occupancy maior que capacity"),
    ({"category": ["bar"]}, "category: definido pela API"),
    ({"availabilityLevel": "full"}, "availabilityLevel: definido pela API"),
    ({"priceRange": "barato"}, "priceRange"),
])
def test_invalid_restaurant_is_rejected(api, change, reason):
    body = {**RESTAURANT, "id": f"{RID}-x", **change}
    body = {k: v for k, v in body.items() if v is not None}
    r = api.post("/v1/restaurants", json=body)
    assert r.status_code == 400
    assert reason in errors(r)


def test_occupancy_update_recomputes_level(api, venues):
    assert api.patch(f"/v1/restaurants/{RID}", json={"occupancy": 60}).json()["availabilityLevel"] == "limited"
    assert api.patch(f"/v1/restaurants/{RID}", json={"occupancy": 80}).json()["availabilityLevel"] == "full"
    assert api.patch(f"/v1/restaurants/{RID}", json={"capacity": 160}).json()["availabilityLevel"] == "available"
    assert api.patch(f"/v1/restaurants/{RID}", json={"occupancy": 161}).status_code == 400
    assert api.patch(f"/v1/restaurants/{RID}", json={"availabilityLevel": "full"}).status_code == 400


def test_list_filters(api, venues):
    def ids(path, **params):
        return [v["id"] for v in api.get(path, params=params).json()]

    assert RID in ids("/v1/restaurants", cuisine="regional", priceRange="$$")
    assert RID not in ids("/v1/restaurants", cuisine="japonesa")
    assert BID in ids("/v1/bars", availability="limited", near="-35.2062,-5.8688", maxDistance=500)
    assert BID not in ids("/v1/bars", availability="full")
