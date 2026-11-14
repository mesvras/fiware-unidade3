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

router = APIRouter(prefix="/v1/beaches", tags=["Praias"])

BEACH = "Beach"
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
REFS = (("PointOfInterest", "refBeach"), ("Event", "refPointOfInterest"), ("BathingReport", "refBeach"), ("BathingStatus", "refBeach"))
Format = Literal["simple", "normalized"]


async def check_station(orion: Orion, body: dict) -> None:
    station = body.get("refWeatherStation")
    if not isinstance(station, str):
        return
    target = await orion.get(station if station.startswith("urn:") else urn("PointOfInterest", station))
    if target is None or "weatherStation" not in (value(target, "category") or []):
        raise ApiError(400, f"refWeatherStation: estação meteorológica {station} não encontrada")


async def read(orion: Orion, beach_id: str) -> dict:
    return await service.read(orion, BEACH, beach_id, "praia")


@router.post("", status_code=201, openapi_extra=body_schema(BEACH))
async def create_beach(request: Request, response: Response, orion: Orion = Depends(get_orion), principal: Principal = Depends(current_principal)):
    body = await service.json_body(request)
    if not isinstance(body.get("id"), str) or not SHORT_ID.match(body["id"]):
        raise ApiError(400, "id: use letras, números, ponto, hífen ou sublinhado")
    await check_station(orion, body)
    entity = await service.create(orion, BEACH, body, principal.owner)
    response.headers["Location"] = f"/v1/beaches/{body['id']}"
    return service.present(entity, "simple")


@router.get("")
async def list_beaches(beachType: str | None = None, facilities: str | None = None, accessType: str | None = None,
                       occupationRate: str | None = None, near: str | None = Query(None, description="longitude,latitude"),
                       maxDistance: int | None = Query(None, ge=1), limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0),
                       format: Format = "simple", orion: Orion = Depends(get_orion)):
    terms = [query.eq(attr, v) for attr, v in (("beachType", beachType), ("facilities", facilities), ("accessType", accessType),
                                               ("occupationRate", occupationRate)) if v]
    found = await orion.query(query.params(BEACH, terms, limit, offset, near, maxDistance))
    return [service.present(e, format) for e in found]


@router.get("/{beach_id}")
async def get_beach(beach_id: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
    return service.present(await read(orion, beach_id), format)


@router.patch("/{beach_id}", openapi_extra=body_schema(BEACH, partial=True, with_id=False))
async def update_beach(beach_id: str, request: Request, orion: Orion = Depends(get_orion), principal: Principal = Depends(current_principal)):
    current = await read(orion, beach_id)
    body = await service.json_body(request)
    await check_station(orion, body)
    return service.present(await service.update(orion, current, principal, body), "simple")


@router.delete("/{beach_id}", status_code=204)
async def delete_beach(beach_id: str, orion: Orion = Depends(get_orion), principal: Principal = Depends(current_principal)):
    current = await read(orion, beach_id)
    await service.ensure_unreferenced(orion, current, REFS, "praia")
    await service.remove(orion, principal, current)
