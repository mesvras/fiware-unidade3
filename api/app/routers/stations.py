import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import query, service
from ..convert import urn, value
from ..auth import Principal
from ..deps import current_principal, get_orion
from ..errors import ApiError
from ..openapi import body_schema
from ..orion import Orion

POI = "PointOfInterest"
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
FOOD = ("capacity", "occupancy", "availabilityLevel", "cuisine", "priceRange", "openingHoursSpecification")
Format = Literal["simple", "normalized"]


def make_router(prefix: str, category: str, tag: str, label: str, with_beach: bool, refs: tuple[tuple[str, str], ...]) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    blocked = ("category", *FOOD, *(() if with_beach else ("refBeach",)))
    exclude = ("category", "availabilityLevel", *FOOD, *(() if with_beach else ("refBeach",)))

    def is_category(e: dict) -> bool:
        return category in (value(e, "category") or [])

    def reject(body: dict) -> None:
        found = [k for k in blocked if k in body]
        if found:
            raise ApiError(400, *(f"{k}: não se aplica a {label}" if k != "category" else "category: definido pela API" for k in found))

    async def read(orion: Orion, item_id: str) -> dict:
        return await service.read(orion, POI, item_id, label, match=is_category)

    @router.post("", status_code=201, openapi_extra=body_schema(POI, exclude=exclude))
    async def create(request: Request, response: Response, orion: Orion = Depends(get_orion), principal: Principal = Depends(current_principal)):
        body = await service.json_body(request)
        reject(body)
        if not isinstance(body.get("id"), str) or not SHORT_ID.match(body["id"]):
            raise ApiError(400, "id: use letras, números, ponto, hífen ou sublinhado")
        entity = await service.create(orion, POI, body, principal.owner, {"category": [category]})
        response.headers["Location"] = f"{prefix}/{body['id']}"
        return service.present(entity, "simple")

    @router.get("")
    async def list_items(beach: str | None = Query(None, include_in_schema=with_beach), near: str | None = Query(None, description="longitude,latitude"),
                         maxDistance: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0),
                         format: Format = "simple", orion: Orion = Depends(get_orion)):
        terms = [query.eq("category", category)]
        if beach and with_beach:
            terms.append(query.eq("refBeach", urn("Beach", beach)))
        found = await orion.query(query.params(POI, terms, limit, offset, near, maxDistance))
        return [service.present(e, format) for e in found]

    @router.get("/{item_id}")
    async def get_item(item_id: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
        return service.present(await read(orion, item_id), format)

    @router.patch("/{item_id}", openapi_extra=body_schema(POI, exclude=exclude, partial=True, with_id=False))
    async def update_item(item_id: str, request: Request, orion: Orion = Depends(get_orion), principal: Principal = Depends(current_principal)):
        current = await read(orion, item_id)
        body = await service.json_body(request)
        reject(body)
        return service.present(await service.update(orion, current, principal, body), "simple")

    @router.delete("/{item_id}", status_code=204)
    async def delete_item(item_id: str, orion: Orion = Depends(get_orion), principal: Principal = Depends(current_principal)):
        current = await read(orion, item_id)
        await service.ensure_unreferenced(orion, current, refs, label)
        await service.remove(orion, principal, current)

    return router


sampling_points = make_router("/v1/sampling-points", "bathingSamplingPoint", "Pontos de coleta", "ponto de coleta", True,
                              (("WaterQualityObserved", "refPointOfInterest"), ("BathingReport", "refPointOfInterest")))
weather_stations = make_router("/v1/weather-stations", "weatherStation", "Estações meteorológicas", "estação meteorológica", False,
                               (("Beach", "refWeatherStation"), ("WeatherObserved", "refPointOfInterest")))
