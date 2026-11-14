import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import query, service
from ..convert import urn
from ..deps import current_owner, get_orion
from ..errors import ApiError
from ..openapi import body_schema
from ..orion import Orion

router = APIRouter(prefix="/v1/hotels", tags=["Hotéis"])

HOTEL, ROOM, AVAIL = "Hotel", "RoomType", "RoomAvailability"
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
Format = Literal["simple", "normalized"]
ROOM_TYPE_FIELD = {"roomType": {"type": "string", "pattern": SHORT_ID.pattern, "description": "Id curto do tipo de quarto"}}


def short_id(value, field: str = "id") -> str:
    if not isinstance(value, str) or not SHORT_ID.match(value):
        raise ApiError(400, f"{field}: use letras, números, ponto, hífen ou sublinhado")
    return value


def compact_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%Y%m%d")
    except (TypeError, ValueError):
        raise ApiError(400, "stayDate: esperado AAAA-MM-DD")


def iso_date(value: str, field: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ApiError(400, f"{field}: esperado AAAA-MM-DD")


def show_room(e: dict, hotel_id: str, fmt: str) -> dict:
    return service.present(e, fmt, prefix=f"{hotel_id}:", drop=("refHotel",))


def show_avail(e: dict, hotel_id: str, fmt: str) -> dict:
    return service.present(e, fmt, prefix=f"{hotel_id}:", drop=("refHotel",), rename={"refRoomType": ("roomType", f"{hotel_id}:")})


@router.post("", status_code=201, openapi_extra=body_schema(HOTEL))
async def create_hotel(request: Request, response: Response, orion: Orion = Depends(get_orion), owner: str = Depends(current_owner)):
    body = await service.json_body(request)
    short_id(body.get("id"))
    entity = await service.create(orion, HOTEL, body, owner)
    response.headers["Location"] = f"/v1/hotels/{body['id']}"
    return service.present(entity, "simple")


@router.get("")
async def list_hotels(category: str | None = None, near: str | None = Query(None, description="longitude,latitude"),
                      maxDistance: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0),
                      format: Format = "simple", orion: Orion = Depends(get_orion)):
    terms = [query.eq("category", category)] if category else []
    found = await orion.query(query.params(HOTEL, terms, limit, offset, near, maxDistance))
    return [service.present(e, format) for e in found]


@router.get("/{hotel_id}")
async def get_hotel(hotel_id: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
    return service.present(await service.read(orion, HOTEL, hotel_id, "hotel"), format)


@router.patch("/{hotel_id}", openapi_extra=body_schema(HOTEL, partial=True, with_id=False))
async def update_hotel(hotel_id: str, request: Request, orion: Orion = Depends(get_orion)):
    current = await service.read(orion, HOTEL, hotel_id, "hotel")
    return service.present(await service.update(orion, current, await service.json_body(request)), "simple")


@router.delete("/{hotel_id}", status_code=204)
async def delete_hotel(hotel_id: str, orion: Orion = Depends(get_orion)):
    current = await service.read(orion, HOTEL, hotel_id, "hotel")
    await service.ensure_unreferenced(orion, current, ((ROOM, "refHotel"),), "hotel")
    await service.remove(orion, current)


@router.post("/{hotel_id}/room-types", status_code=201, openapi_extra=body_schema(ROOM, exclude=("refHotel",)))
async def create_room_type(hotel_id: str, request: Request, response: Response, orion: Orion = Depends(get_orion),
                           owner: str = Depends(current_owner)):
    await service.read(orion, HOTEL, hotel_id, "hotel")
    body = await service.json_body(request)
    if "refHotel" in body:
        raise ApiError(400, "refHotel: definido pela URL")
    room_id = short_id(body.get("id"))
    entity = await service.create(orion, ROOM, {**body, "id": f"{hotel_id}:{room_id}"}, owner, {"refHotel": hotel_id})
    response.headers["Location"] = f"/v1/hotels/{hotel_id}/room-types/{room_id}"
    return show_room(entity, hotel_id, "simple")


@router.get("/{hotel_id}/room-types")
async def list_room_types(hotel_id: str, adults: int | None = Query(None, ge=1), children: int | None = Query(None, ge=0),
                          limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0), format: Format = "simple",
                          orion: Orion = Depends(get_orion)):
    terms = [query.eq("refHotel", urn(HOTEL, hotel_id))]
    if adults is not None:
        terms.append(f"maxAdults>={adults}")
    if children is not None:
        terms.append(f"maxChildren>={children}")
    found = await orion.query(query.params(ROOM, terms, limit, offset))
    return [show_room(e, hotel_id, format) for e in found]


@router.get("/{hotel_id}/room-types/{room_id}")
async def get_room_type(hotel_id: str, room_id: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
    return show_room(await service.read(orion, ROOM, f"{hotel_id}:{room_id}", "tipo de quarto"), hotel_id, format)


@router.patch("/{hotel_id}/room-types/{room_id}", openapi_extra=body_schema(ROOM, exclude=("refHotel",), partial=True, with_id=False))
async def update_room_type(hotel_id: str, room_id: str, request: Request, orion: Orion = Depends(get_orion)):
    current = await service.read(orion, ROOM, f"{hotel_id}:{room_id}", "tipo de quarto")
    updated = await service.update(orion, current, await service.json_body(request), frozen=("refHotel",))
    return show_room(updated, hotel_id, "simple")


@router.delete("/{hotel_id}/room-types/{room_id}", status_code=204)
async def delete_room_type(hotel_id: str, room_id: str, orion: Orion = Depends(get_orion)):
    current = await service.read(orion, ROOM, f"{hotel_id}:{room_id}", "tipo de quarto")
    await service.ensure_unreferenced(orion, current, ((AVAIL, "refRoomType"),), "tipo de quarto")
    await service.remove(orion, current)


@router.post("/{hotel_id}/availability", status_code=201,
             openapi_extra=body_schema(AVAIL, exclude=("refHotel", "refRoomType"), extra=ROOM_TYPE_FIELD, with_id=False))
async def create_availability(hotel_id: str, request: Request, response: Response, orion: Orion = Depends(get_orion),
                              owner: str = Depends(current_owner)):
    await service.read(orion, HOTEL, hotel_id, "hotel")
    body = await service.json_body(request)
    for field in ("id", "refHotel", "refRoomType"):
        if field in body:
            raise ApiError(400, f"{field}: definido pela URL e por roomType e stayDate")
    room_id = short_id(body.pop("roomType", None), "roomType")
    await service.read(orion, ROOM, f"{hotel_id}:{room_id}", "tipo de quarto")
    day = compact_date(body.get("stayDate"))
    fixed = {"id": f"{hotel_id}:{room_id}:{day}", "refHotel": hotel_id, "refRoomType": f"{hotel_id}:{room_id}"}
    entity = await service.create(orion, AVAIL, body, owner, fixed)
    response.headers["Location"] = f"/v1/hotels/{hotel_id}/availability/{room_id}/{body['stayDate']}"
    return show_avail(entity, hotel_id, "simple")


@router.get("/{hotel_id}/availability")
async def list_availability(hotel_id: str, from_: str | None = Query(None, alias="from", description="AAAA-MM-DD, inclusivo"),
                            to: str | None = Query(None, description="AAAA-MM-DD, exclusivo"), roomType: str | None = None,
                            limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), format: Format = "simple",
                            orion: Orion = Depends(get_orion)):
    terms = [query.eq("refHotel", urn(HOTEL, hotel_id))]
    if roomType:
        terms.append(query.eq("refRoomType", urn(ROOM, f"{hotel_id}:{short_id(roomType, 'roomType')}")))
    terms += query.date_range("stayDate", from_ and iso_date(from_, "from"), to and iso_date(to, "to"))
    found = await orion.query(query.params(AVAIL, terms, limit, offset))
    return [show_avail(e, hotel_id, format) for e in found]


@router.get("/{hotel_id}/availability/{room_id}/{stay_date}")
async def get_availability(hotel_id: str, room_id: str, stay_date: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
    current = await service.read(orion, AVAIL, f"{hotel_id}:{room_id}:{compact_date(stay_date)}", "disponibilidade")
    return show_avail(current, hotel_id, format)


@router.patch("/{hotel_id}/availability/{room_id}/{stay_date}",
              openapi_extra=body_schema(AVAIL, exclude=("refHotel", "refRoomType", "stayDate"), partial=True, with_id=False))
async def update_availability(hotel_id: str, room_id: str, stay_date: str, request: Request, orion: Orion = Depends(get_orion)):
    current = await service.read(orion, AVAIL, f"{hotel_id}:{room_id}:{compact_date(stay_date)}", "disponibilidade")
    updated = await service.update(orion, current, await service.json_body(request), frozen=("refHotel", "refRoomType", "stayDate", "roomType"))
    return show_avail(updated, hotel_id, "simple")


@router.delete("/{hotel_id}/availability/{room_id}/{stay_date}", status_code=204)
async def delete_availability(hotel_id: str, room_id: str, stay_date: str, orion: Orion = Depends(get_orion)):
    current = await service.read(orion, AVAIL, f"{hotel_id}:{room_id}:{compact_date(stay_date)}", "disponibilidade")
    await service.remove(orion, current)
