import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import query, service
from ..config import settings
from ..convert import value
from ..deps import current_owner, get_orion
from ..errors import ApiError
from ..openapi import body_schema
from ..orion import Orion

POI = "PointOfInterest"
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
DERIVED = ("category", "availabilityLevel")
Format = Literal["simple", "normalized"]
Level = Literal["available", "limited", "full"]


def availability_level(entity: dict) -> dict:
    capacity, occupancy = value(entity, "capacity"), value(entity, "occupancy")
    if not isinstance(capacity, int) or not isinstance(occupancy, int) or capacity < 1:
        return {}
    if occupancy >= capacity:
        level = "full"
    elif occupancy / capacity >= settings.limited_ratio:
        level = "limited"
    else:
        level = "available"
    return {"availabilityLevel": {"type": "Property", "value": level}}


def reject_derived(body: dict) -> None:
    blocked = [k for k in DERIVED if k in body]
    if blocked:
        raise ApiError(400, *(f"{k}: definido pela API" for k in blocked))


def make_router(prefix: str, category: str, tag: str, label: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    def is_category(e: dict) -> bool:
        return category in (value(e, "category") or [])

    async def read(orion: Orion, item_id: str) -> dict:
        return await service.read(orion, POI, item_id, label, match=is_category)

    @router.post("", status_code=201, openapi_extra=body_schema(POI, exclude=("category", "availabilityLevel", "refBeach")))
    async def create(request: Request, response: Response, orion: Orion = Depends(get_orion), owner: str = Depends(current_owner)):
        body = await service.json_body(request)
        reject_derived(body)
        if not isinstance(body.get("id"), str) or not SHORT_ID.match(body["id"]):
            raise ApiError(400, "id: use letras, números, ponto, hífen ou sublinhado")
        entity = await service.create(orion, POI, body, owner, {"category": [category]}, derive=availability_level)
        response.headers["Location"] = f"{prefix}/{body['id']}"
        return service.present(entity, "simple")

    @router.get("")
    async def list_items(availability: Level | None = None, cuisine: str | None = None, priceRange: str | None = None,
                         near: str | None = Query(None, description="longitude,latitude"), maxDistance: int | None = Query(None, ge=1),
                         limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0), format: Format = "simple",
                         orion: Orion = Depends(get_orion)):
        terms = [query.eq("category", category)]
        for attr, v in (("availabilityLevel", availability), ("cuisine", cuisine), ("priceRange", priceRange)):
            if v:
                terms.append(query.eq(attr, v))
        found = await orion.query(query.params(POI, terms, limit, offset, near, maxDistance))
        return [service.present(e, format) for e in found]

    @router.get("/{item_id}")
    async def get_item(item_id: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
        return service.present(await read(orion, item_id), format)

    @router.patch("/{item_id}", openapi_extra=body_schema(POI, exclude=("category", "availabilityLevel", "refBeach"), partial=True, with_id=False))
    async def update_item(item_id: str, request: Request, orion: Orion = Depends(get_orion)):
        current = await read(orion, item_id)
        body = await service.json_body(request)
        reject_derived(body)
        return service.present(await service.update(orion, current, body, derive=availability_level), "simple")

    @router.delete("/{item_id}", status_code=204)
    async def delete_item(item_id: str, orion: Orion = Depends(get_orion)):
        await service.remove(orion, await read(orion, item_id))

    return router


restaurants = make_router("/v1/restaurants", "restaurant", "Restaurantes", "restaurante")
bars = make_router("/v1/bars", "bar", "Bares", "bar")
