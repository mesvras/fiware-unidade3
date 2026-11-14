import asyncio
import dataclasses

import pytest

from app.config import settings
from app.convert import to_ngsi
from app.orion import Orion, OrionError
from app.validation import ValidationFailed, validate

TENANT = "apitest"
HOTEL = to_ngsi("Hotel", {"id": "teste-hotel", "name": "Hotel Teste", "location": [-35.2, -5.87],
                          "address": {"addressLocality": "Natal"}, "dataOwner": "org-teste"})
ROOM = to_ngsi("RoomType", {"id": "teste-hotel:std", "name": "Standard", "refHotel": "teste-hotel", "dataOwner": "org-teste",
                            "maxAdults": 2, "maxChildren": 1, "totalUnits": 5})


def avail(units: int) -> dict:
    return to_ngsi("RoomAvailability", {"id": "teste-hotel:std:20261220", "refHotel": "teste-hotel", "refRoomType": "teste-hotel:std",
                                        "dataOwner": "org-teste", "stayDate": "2026-12-20", "availableUnits": units,
                                        "pricePerNight": {"value": 300.0, "currency": "BRL"}})


async def scenario():
    orion = Orion(dataclasses.replace(settings, tenant=TENANT))
    try:
        for e in (ROOM, HOTEL):
            await orion.delete(e["id"])
        await orion.create(HOTEL)
        await orion.create(ROOM)
        with pytest.raises(OrionError) as dup:
            await orion.create(HOTEL)
        got = await orion.get(HOTEL["id"])
        await validate(orion, avail(5))
        with pytest.raises(ValidationFailed) as too_many:
            await validate(orion, avail(9))
        with pytest.raises(ValidationFailed) as missing_ref:
            await validate(orion, to_ngsi("RoomType", {"id": "x:y", "name": "N", "refHotel": "inexistente", "dataOwner": "o-1",
                                                       "maxAdults": 1, "maxChildren": 0, "totalUnits": 1}))
        await orion.update(HOTEL["id"], {"name": {"type": "Property", "value": "Hotel Teste 2"}})
        updated = await orion.get(HOTEL["id"])
        listed = await orion.query({"type": "Hotel"})
        deleted = await orion.delete(HOTEL["id"])
        gone = await orion.get(HOTEL["id"])
        await orion.delete(ROOM["id"])
        return dup.value, got, too_many.value, missing_ref.value, updated, listed, deleted, gone
    finally:
        await orion.close()


def test_orion_crud_and_validation_with_related_entities():
    dup, got, too_many, missing_ref, updated, listed, deleted, gone = asyncio.run(scenario())
    assert dup.status == 409
    assert got == HOTEL
    assert any("availableUnits maior que totalUnits" in x for x in too_many.errors)
    assert any("entidade inexistente urn:ngsi-ld:Hotel:inexistente" in x for x in missing_ref.errors)
    assert updated["name"]["value"] == "Hotel Teste 2"
    assert [e["id"] for e in listed] == [HOTEL["id"]]
    assert deleted is True
    assert gone is None
