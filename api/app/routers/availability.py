from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from .. import query
from ..convert import slug_of, value
from ..deps import get_orion
from ..errors import ApiError
from ..orion import Orion

router = APIRouter(prefix="/v1/availability", tags=["Disponibilidade"])

MAX_NIGHTS = 30
LIMIT = 1000


def parse(day: str, field: str) -> date:
    try:
        return date.fromisoformat(day)
    except ValueError:
        raise ApiError(400, f"{field}: esperado AAAA-MM-DD")


def fits(room: dict, adults: int, children: int, rooms: int) -> bool:
    max_adults, max_children = value(room, "maxAdults") or 0, value(room, "maxChildren") or 0
    return adults <= max_adults * rooms and adults + children <= (max_adults + max_children) * rooms


@router.get("", summary="Busca quartos livres em todas as noites de um período para um grupo")
async def search(checkIn: str = Query(..., description="AAAA-MM-DD"), checkOut: str = Query(..., description="AAAA-MM-DD, posterior a checkIn"),
                 adults: int = Query(1, ge=1), children: int = Query(0, ge=0), rooms: int = Query(1, ge=1),
                 orion: Orion = Depends(get_orion)):
    start, end = parse(checkIn, "checkIn"), parse(checkOut, "checkOut")
    nights = (end - start).days
    if nights < 1:
        raise ApiError(400, "checkOut deve ser posterior a checkIn")
    if nights > MAX_NIGHTS:
        raise ApiError(400, f"período máximo de {MAX_NIGHTS} noites")
    wanted = {(start + timedelta(days=i)).isoformat() for i in range(nights)}

    room_types = {e["id"]: e for e in await orion.query({"type": "RoomType", "limit": LIMIT}) if fits(e, adults, children, rooms)}
    terms = query.date_range("stayDate", start.isoformat(), end.isoformat()) + [f"availableUnits>={rooms}"]
    records = await orion.query(query.params("RoomAvailability", terms, LIMIT, 0))

    by_room: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        room_id = r["refRoomType"]["object"]
        if room_id in room_types:
            by_room[room_id].append(r)

    hotels = await orion.get_many([room_types[r]["refHotel"]["object"] for r in by_room])
    offers = []
    for room_id, recs in by_room.items():
        days = {value(r, "stayDate"): r for r in recs}
        if set(days) != wanted or any((value(r, "minimumStay") or 1) > nights for r in recs):
            continue
        currencies = {r["pricePerNight"]["currency"]["value"] for r in recs}
        if len(currencies) != 1:
            continue
        room = room_types[room_id]
        hotel_urn = room["refHotel"]["object"]
        hotel_id = slug_of("Hotel", hotel_urn)
        offers.append({
            "hotel": hotel_id,
            "hotelName": value(hotels.get(hotel_urn, {}), "name"),
            "roomType": slug_of("RoomType", room_id)[len(hotel_id) + 1:],
            "roomTypeName": value(room, "name"),
            "nights": nights,
            "rooms": rooms,
            "availableUnits": min(value(r, "availableUnits") for r in recs),
            "totalPrice": {"value": round(sum(value(r, "pricePerNight") for r in recs) * rooms, 2), "currency": currencies.pop()},
            "pricePerNight": [{"stayDate": d, "value": value(days[d], "pricePerNight")} for d in sorted(days)],
        })
    return sorted(offers, key=lambda o: (o["totalPrice"]["value"], o["hotel"], o["roomType"]))
