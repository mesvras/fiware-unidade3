import os
import uuid

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://api:8000")
HID = f"teste-{uuid.uuid4().hex[:8]}"
HOTEL = {"id": HID, "name": "Hotel Teste", "location": [-35.205, -5.87], "address": {"addressLocality": "Natal"},
         "category": "hotel", "starRating": 4, "checkInTime": "14:00", "dataOwner": "intruso"}
ROOMS = [
    {"id": "std", "name": "Standard", "maxAdults": 2, "maxChildren": 1, "totalUnits": 5},
    {"id": "fam", "name": "Família", "maxAdults": 3, "maxChildren": 2, "totalUnits": 2},
]
NIGHTS = [
    {"roomType": "std", "stayDate": "2026-12-20", "availableUnits": 3, "pricePerNight": {"value": 300.0, "currency": "BRL"}},
    {"roomType": "std", "stayDate": "2026-12-21", "availableUnits": 1, "pricePerNight": {"value": 320.0, "currency": "BRL"}},
    {"roomType": "fam", "stayDate": "2026-12-20", "availableUnits": 2, "pricePerNight": {"value": 500.0, "currency": "BRL"}},
]


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=API_URL, timeout=20) as client:
        yield client


@pytest.fixture(scope="module")
def hotel(api):
    assert api.post("/v1/hotels", json=HOTEL).status_code == 201
    for room in ROOMS:
        assert api.post(f"/v1/hotels/{HID}/room-types", json=room).status_code == 201
    for night in NIGHTS:
        assert api.post(f"/v1/hotels/{HID}/availability", json=night).status_code == 201
    yield HID
    for night in NIGHTS:
        api.delete(f"/v1/hotels/{HID}/availability/{night['roomType']}/{night['stayDate']}")
    for room in ROOMS:
        api.delete(f"/v1/hotels/{HID}/room-types/{room['id']}")
    api.delete(f"/v1/hotels/{HID}")


def errors(r: httpx.Response) -> str:
    return " | ".join(r.json()["errors"])


def test_hotel_is_created_with_owner_from_api(api, hotel):
    r = api.get(f"/v1/hotels/{hotel}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == hotel
    assert body["dataOwner"] == "dev-owner"
    assert body["location"] == HOTEL["location"]


def test_hotel_normalized_format(api, hotel):
    body = api.get(f"/v1/hotels/{hotel}", params={"format": "normalized"}).json()
    assert body["id"] == f"urn:ngsi-ld:Hotel:{hotel}"
    assert body["starRating"] == {"type": "Property", "value": 4}


def test_duplicate_hotel_conflicts(api, hotel):
    assert api.post("/v1/hotels", json=HOTEL).status_code == 409


@pytest.mark.parametrize("change,reason", [
    ({"starRating": 7}, "starRating"),
    ({"starRatin": 4}, "starRatin: atributo desconhecido"),
    ({"location": [-5.87]}, "longitude, latitude"),
    ({"id": "com:dois-pontos"}, "id: use letras"),
])
def test_invalid_hotel_is_rejected(api, change, reason):
    r = api.post("/v1/hotels", json={**HOTEL, "id": f"{HID}-x", **change})
    assert r.status_code == 400
    assert reason in errors(r)


def test_hotel_list_filters_by_category_and_distance(api, hotel):
    ids = [h["id"] for h in api.get("/v1/hotels", params={"category": "hotel", "near": "-35.205,-5.87", "maxDistance": 500}).json()]
    assert hotel in ids
    far = [h["id"] for h in api.get("/v1/hotels", params={"near": "-35.0,-5.5", "maxDistance": 500}).json()]
    assert hotel not in far


def test_hotel_update(api, hotel):
    r = api.patch(f"/v1/hotels/{hotel}", json={"name": "Hotel Teste Renovado"})
    assert r.status_code == 200
    assert api.get(f"/v1/hotels/{hotel}").json()["name"] == "Hotel Teste Renovado"
    assert api.patch(f"/v1/hotels/{hotel}", json={"id": "outro"}).status_code == 400
    assert api.patch(f"/v1/hotels/{hotel}", json={"starRating": 9}).status_code == 400


def test_missing_hotel_is_404(api):
    assert api.get("/v1/hotels/nao-existe").status_code == 404
    assert api.post("/v1/hotels/nao-existe/room-types", json=ROOMS[0]).status_code == 404


def test_room_types_are_nested_and_filtered(api, hotel):
    rooms = api.get(f"/v1/hotels/{hotel}/room-types").json()
    assert sorted(r["id"] for r in rooms) == ["fam", "std"]
    assert all("refHotel" not in r for r in rooms)
    assert [r["id"] for r in api.get(f"/v1/hotels/{hotel}/room-types", params={"adults": 3}).json()] == ["fam"]
    r = api.post(f"/v1/hotels/{hotel}/room-types", json={**ROOMS[0], "id": "x", "refHotel": "outro"})
    assert r.status_code == 400


def test_availability_rules(api, hotel):
    r = api.post(f"/v1/hotels/{hotel}/availability", json={**NIGHTS[0], "stayDate": "2026-12-25", "availableUnits": 9})
    assert r.status_code == 400
    assert "availableUnits maior que totalUnits" in errors(r)
    assert api.post(f"/v1/hotels/{hotel}/availability", json={**NIGHTS[0], "roomType": "nao-existe"}).status_code == 404
    assert api.post(f"/v1/hotels/{hotel}/availability", json=NIGHTS[0]).status_code == 409


def test_availability_list_and_item(api, hotel):
    listed = api.get(f"/v1/hotels/{hotel}/availability", params={"from": "2026-12-21", "to": "2026-12-22"}).json()
    assert [(a["roomType"], a["stayDate"]) for a in listed] == [("std", "2026-12-21")]
    item = api.get(f"/v1/hotels/{hotel}/availability/std/2026-12-20").json()
    assert item["id"] == "std:20261220"
    assert item["pricePerNight"] == {"value": 300.0, "currency": "BRL"}
    assert api.patch(f"/v1/hotels/{hotel}/availability/std/2026-12-20", json={"availableUnits": 4}).json()["availableUnits"] == 4
    assert api.patch(f"/v1/hotels/{hotel}/availability/std/2026-12-20", json={"availableUnits": 6}).status_code == 400
    assert api.patch(f"/v1/hotels/{hotel}/availability/std/2026-12-20", json={"stayDate": "2026-12-24"}).status_code == 400


def test_search_by_period_and_group(api, hotel):
    def offers(**params):
        return [o for o in api.get("/v1/availability", params=params).json() if o["hotel"] == hotel]

    two_nights = offers(checkIn="2026-12-20", checkOut="2026-12-22", adults=2, children=1)
    assert [(o["roomType"], o["totalPrice"]) for o in two_nights] == [("std", {"value": 620.0, "currency": "BRL"})]
    assert two_nights[0]["availableUnits"] == 1
    assert [o["roomType"] for o in offers(checkIn="2026-12-20", checkOut="2026-12-21", adults=3)] == ["fam"]
    assert offers(checkIn="2026-12-20", checkOut="2026-12-22", adults=3) == []
    assert offers(checkIn="2026-12-21", checkOut="2026-12-22", adults=2, rooms=2) == []
    assert api.get("/v1/availability", params={"checkIn": "2026-12-22", "checkOut": "2026-12-20"}).status_code == 400


def test_delete_requires_children_removed_first(api, hotel):
    assert api.delete(f"/v1/hotels/{hotel}").status_code == 409
    assert api.delete(f"/v1/hotels/{hotel}/room-types/fam").status_code == 409
