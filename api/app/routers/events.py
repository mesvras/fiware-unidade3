import re
from datetime import datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import query, service
from ..convert import urn, value
from ..deps import current_owner, get_orion
from ..errors import ApiError
from ..openapi import body_schema
from ..orion import Orion

router = APIRouter(prefix="/v1/events", tags=["Eventos"])

EVENT, POI, BEACH = "Event", "PointOfInterest", "Beach"
RESTRICTION = "bathingRestriction"
SHORT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
PLACES = {"restaurant": (POI, "restaurant"), "bar": (POI, "bar"), "beach": (BEACH, None)}
Format = Literal["simple", "normalized"]
PLACE_FIELD = {"refPointOfInterest": {"oneOf": [
    {"type": "string", "description": "URN de Beach ou PointOfInterest"},
    {"type": "object", "minProperties": 1, "maxProperties": 1, "additionalProperties": False,
     "properties": {k: {"type": "string"} for k in PLACES}, "description": "Forma curta: {\"bar\": id}, {\"restaurant\": id} ou {\"beach\": id}"},
]}}


def is_event(e: dict) -> bool:
    return RESTRICTION not in (value(e, "category") or [])


def utc(text: str, field: str) -> str:
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, f"{field}: esperado AAAA-MM-DD ou AAAA-MM-DDTHH:MM:SSZ")
    if len(text) == 10:
        moment = datetime.combine(moment.date(), time(), timezone.utc)
    if moment.tzinfo is None:
        raise ApiError(400, f"{field}: informe o fuso, por exemplo Z")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def resolve_place(orion: Orion, body: dict) -> dict:
    place = body.get("refPointOfInterest")
    if not isinstance(place, dict):
        return body
    if len(place) != 1 or next(iter(place)) not in PLACES:
        raise ApiError(400, f"refPointOfInterest: use um destes campos: {', '.join(PLACES)}")
    kind, slug = next(iter(place.items()))
    type_, category = PLACES[kind]
    target = await orion.get(urn(type_, slug)) if isinstance(slug, str) else None
    if target is None or target.get("type") != type_ or (category and category not in (value(target, "category") or [])):
        raise ApiError(400, f"refPointOfInterest: {kind} {slug} não encontrado")
    return {**body, "refPointOfInterest": target["id"]}


def reject_restriction(body: dict) -> None:
    category = body.get("category")
    if isinstance(category, list) and RESTRICTION in category:
        raise ApiError(400, f"category: {RESTRICTION} é registrado em /v1/bathing-restrictions")


async def read(orion: Orion, event_id: str) -> dict:
    return await service.read(orion, EVENT, event_id, "evento", match=is_event)


@router.post("", status_code=201, openapi_extra=body_schema(EVENT, exclude=("refPointOfInterest",), extra=PLACE_FIELD))
async def create_event(request: Request, response: Response, orion: Orion = Depends(get_orion), owner: str = Depends(current_owner)):
    body = await service.json_body(request)
    if not isinstance(body.get("id"), str) or not SHORT_ID.match(body["id"]):
        raise ApiError(400, "id: use letras, números, ponto, hífen ou sublinhado")
    reject_restriction(body)
    entity = await service.create(orion, EVENT, await resolve_place(orion, body), owner)
    response.headers["Location"] = f"/v1/events/{body['id']}"
    return service.present(entity, "simple")


@router.get("", summary="Agenda: eventos que se sobrepõem à janela, em ordem de início")
async def list_events(from_: str | None = Query(None, alias="from", description="Início da janela, AAAA-MM-DD ou DateTime UTC"),
                      to: str | None = Query(None, description="Fim da janela, exclusivo"),
                      category: str | None = None, eventScale: str | None = None, eventStatus: str | None = None,
                      audience: str | None = None, isAccessibleForFree: bool | None = None,
                      near: str | None = Query(None, description="longitude,latitude"), maxDistance: int | None = Query(None, ge=1),
                      limit: int = Query(20, ge=1, le=1000), offset: int = Query(0, ge=0), format: Format = "simple",
                      orion: Orion = Depends(get_orion)):
    start, end = (from_ and utc(from_, "from")), (to and utc(to, "to"))
    if start and end and end <= start:
        raise ApiError(400, "to deve ser posterior a from")
    terms = [f'category!="{RESTRICTION}"']
    if end:
        terms.append(f"startDate[@value]<{query.literal(end)}")
    if start:
        terms.append(f"endDate[@value]>{query.literal(start)}")
    for attr, v in (("category", category), ("eventScale", eventScale), ("eventStatus", eventStatus), ("audience", audience)):
        if v:
            terms.append(query.eq(attr, v))
    if isAccessibleForFree is not None:
        terms.append(f"isAccessibleForFree=={str(isAccessibleForFree).lower()}")
    params = query.params(EVENT, terms, limit, offset, near, maxDistance) | {"local": "true", "orderBy": "startDate"}
    return [service.present(e, format) for e in await orion.query(params)]


@router.get("/{event_id}")
async def get_event(event_id: str, format: Format = "simple", orion: Orion = Depends(get_orion)):
    return service.present(await read(orion, event_id), format)


@router.patch("/{event_id}", openapi_extra=body_schema(EVENT, exclude=("refPointOfInterest",), extra=PLACE_FIELD, partial=True, with_id=False))
async def update_event(event_id: str, request: Request, orion: Orion = Depends(get_orion)):
    current = await read(orion, event_id)
    body = await service.json_body(request)
    reject_restriction(body)
    return service.present(await service.update(orion, current, await resolve_place(orion, body)), "simple")


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: str, orion: Orion = Depends(get_orion)):
    await service.remove(orion, await read(orion, event_id))
