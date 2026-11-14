import pytest

from app.convert import ConversionError, from_ngsi, to_ngsi
from tests.examples import load_examples, without_context

EXAMPLES = load_examples()


@pytest.mark.parametrize("entity", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_round_trip_is_identical(entity):
    simple = from_ngsi(entity)
    assert to_ngsi(entity["type"], simple) == without_context(entity)


def test_simple_hotel_becomes_ngsi_ld():
    e = to_ngsi("Hotel", {"id": "h1", "name": "H", "location": [-35.2, -5.8], "starRating": 4})
    assert e["id"] == "urn:ngsi-ld:Hotel:h1"
    assert e["location"] == {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [-35.2, -5.8]}}
    assert e["starRating"] == {"type": "Property", "value": 4}


def test_relationship_slug_becomes_urn():
    e = to_ngsi("RoomType", {"id": "h1:std", "refHotel": "h1"})
    assert e["refHotel"] == {"type": "Relationship", "object": "urn:ngsi-ld:Hotel:h1"}


def test_ambiguous_relationship_requires_urn():
    with pytest.raises(ConversionError, match="URN completo"):
        to_ngsi("Event", {"id": "e1", "refPointOfInterest": "praia"})


def test_dates_become_typed_values():
    e = to_ngsi("RoomAvailability", {"id": "h:t:20261220", "stayDate": "2026-12-20"})
    assert e["stayDate"]["value"] == {"@type": "Date", "@value": "2026-12-20"}


def test_price_requires_currency_object():
    with pytest.raises(ConversionError, match="currency"):
        to_ngsi("RoomAvailability", {"id": "h:t:20261220", "pricePerNight": 420.0})
    e = to_ngsi("RoomAvailability", {"id": "h:t:20261220", "pricePerNight": {"value": 420.0, "currency": "BRL"}})
    assert e["pricePerNight"]["currency"] == {"type": "Property", "value": "BRL"}


def test_occupancy_without_observed_at_gets_current_time():
    e = to_ngsi("PointOfInterest", {"occupancy": 10}, with_id=False)
    assert e["occupancy"]["value"] == 10
    assert e["occupancy"]["observedAt"].endswith("Z")


def test_unknown_attribute_is_rejected():
    with pytest.raises(ConversionError, match="starRatin: atributo desconhecido"):
        to_ngsi("Hotel", {"id": "h1", "starRatin": 4})


def test_location_must_be_coordinates():
    with pytest.raises(ConversionError, match="longitude, latitude"):
        to_ngsi("Beach", {"id": "b1", "location": {"lat": -5.8, "lon": -35.2}})


def test_patch_cannot_change_id():
    with pytest.raises(ConversionError, match="id: não pode ser alterado"):
        to_ngsi("Hotel", {"id": "outro", "name": "X"}, with_id=False)
