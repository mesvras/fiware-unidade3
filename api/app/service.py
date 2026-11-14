import json
from collections.abc import Callable

from fastapi import Request

from .auth import Principal, ensure_owner
from .convert import from_ngsi, to_ngsi, urn
from .errors import ApiError, not_found
from .orion import Orion
from .validation import validate

OWNER = "dataOwner"


async def json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise ApiError(400, "corpo não é JSON válido")
    if not isinstance(body, dict):
        raise ApiError(400, "o corpo deve ser um objeto JSON")
    return body


Derive = Callable[[dict], dict]


async def create(orion: Orion, type_: str, body: dict, owner: str, fixed: dict | None = None, derive: Derive | None = None) -> dict:
    data = {k: v for k, v in body.items() if k != OWNER}
    entity = to_ngsi(type_, {**data, **(fixed or {}), OWNER: owner})
    if derive:
        entity.update(derive(entity))
    await validate(orion, entity)
    await orion.create(entity)
    return entity


async def read(orion: Orion, type_: str, slug: str, what: str, match: Callable[[dict], bool] | None = None) -> dict:
    entity = await orion.get(urn(type_, slug))
    if entity is None or entity.get("type") != type_ or (match and not match(entity)):
        raise not_found(what)
    return entity


async def update(orion: Orion, current: dict, principal: Principal, body: dict, frozen: tuple[str, ...] = (), derive: Derive | None = None) -> dict:
    ensure_owner(current, principal)
    blocked = sorted(k for k in body if k in frozen)
    if blocked:
        raise ApiError(400, *(f"{k}: não pode ser alterado" for k in blocked))
    changes = to_ngsi(current["type"], {k: v for k, v in body.items() if k != OWNER}, with_id=False)
    if derive:
        changes.update({k: v for k, v in derive({**current, **changes}).items() if current.get(k) != v})
    merged = {**current, **changes}
    await validate(orion, merged)
    if changes:
        await orion.update(current["id"], changes)
    return merged


async def ensure_unreferenced(orion: Orion, entity: dict, refs: tuple[tuple[str, str], ...], what: str) -> None:
    for type_, attr in refs:
        if await orion.query({"type": type_, "q": f"{attr}=={json.dumps(entity['id'])}", "limit": 1}):
            raise ApiError(409, f"{what} ainda é referenciado por {type_}.{attr}")


async def remove(orion: Orion, principal: Principal, entity: dict) -> None:
    ensure_owner(entity, principal)
    await orion.delete(entity["id"])


def present(entity: dict, fmt: str, prefix: str = "", drop: tuple[str, ...] = (), rename: dict | None = None) -> dict:
    if fmt == "normalized":
        return entity
    out = from_ngsi(entity)
    if prefix and out["id"].startswith(prefix):
        out["id"] = out["id"][len(prefix):]
    for k in drop:
        out.pop(k, None)
    for old, (new, cut) in (rename or {}).items():
        if old in out:
            value = out.pop(old)
            out[new] = value[len(cut):] if isinstance(value, str) and value.startswith(cut) else value
    return out
