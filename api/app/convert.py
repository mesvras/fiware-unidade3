import re
from datetime import datetime, timezone

from spec import ENTITIES

PREFIX = "urn:ngsi-ld:"
TYPED = {"datetime": "DateTime", "date": "Date"}


class ConversionError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def urn(type_: str, slug: str) -> str:
    return f"{PREFIX}{type_}:{slug}"


def slug_of(type_: str, id_: str) -> str | None:
    prefix = urn(type_, "")
    return id_[len(prefix):] if id_.startswith(prefix) else None


def targets(attr: dict) -> list[str]:
    return [n for n in ENTITIES if re.search(rf"\b{n}\b", attr["target"])]


def value(entity: dict, attr: str):
    v = entity.get(attr, {}).get("value")
    return v["@value"] if isinstance(v, dict) and "@value" in v else v


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _relationship(attr: dict, v, errors: list[str]):
    name = attr["name"]
    if not isinstance(v, str) or not v:
        errors.append(f"{name}: esperado identificador")
        return None
    if v.startswith(PREFIX):
        return {"type": "Relationship", "object": v}
    candidates = targets(attr)
    if len(candidates) != 1:
        errors.append(f"{name}: informe o URN completo, porque o destino pode ser {' ou '.join(candidates)}")
        return None
    return {"type": "Relationship", "object": urn(candidates[0], v)}


def _geo(attr: dict, v, errors: list[str]):
    if not (isinstance(v, list) and len(v) in (2, 3) and all(_is_number(c) for c in v)):
        errors.append(f"{attr['name']}: esperado [longitude, latitude]")
        return None
    return {"type": "GeoProperty", "value": {"type": "Point", "coordinates": v}}


def _property(attr: dict, v, errors: list[str]):
    name = attr["name"]
    subattrs = attr.get("subattrs", {})
    observed = None
    extra = {}
    if subattrs or attr.get("observed_at"):
        if isinstance(v, dict) and "value" in v:
            unknown = set(v) - {"value", "observedAt", *subattrs}
            if unknown:
                errors.append(f"{name}: campos desconhecidos {', '.join(sorted(unknown))}")
                return None
            observed = v.get("observedAt")
            extra = {k: v[k] for k in subattrs if k in v}
            v = v["value"]
        elif subattrs:
            errors.append(f"{name}: esperado objeto com value e {', '.join(subattrs)}")
            return None
    if attr["vtype"] in TYPED:
        if not isinstance(v, str):
            errors.append(f"{name}: esperado texto com a data")
            return None
        v = {"@type": TYPED[attr["vtype"]], "@value": v}
    out = {"type": "Property", "value": v}
    for k, sv in extra.items():
        out[k] = {"type": "Property", "value": sv}
    if observed is not None:
        out["observedAt"] = observed
    elif attr.get("observed_at"):
        out["observedAt"] = now()
    return out


def attr_to_ngsi(attr: dict, v, errors: list[str]):
    if attr["kind"] == "R":
        return _relationship(attr, v, errors)
    if attr["kind"] == "G":
        return _geo(attr, v, errors)
    return _property(attr, v, errors)


def to_ngsi(type_: str, body, with_id: bool = True) -> dict:
    if type_ not in ENTITIES:
        raise ConversionError([f"tipo desconhecido: {type_}"])
    if not isinstance(body, dict):
        raise ConversionError(["o corpo deve ser um objeto JSON"])
    attrs = {a["name"]: a for a in ENTITIES[type_]["attrs"]}
    errors: list[str] = []
    out: dict = {}
    if with_id:
        slug = body.get("id")
        if not isinstance(slug, str) or not slug:
            errors.append("id: obrigatório")
        else:
            out["id"] = urn(type_, slug)
        out["type"] = type_
    elif "id" in body:
        errors.append("id: não pode ser alterado")
    for k, v in body.items():
        if k == "id":
            continue
        attr = attrs.get(k)
        if attr is None:
            errors.append(f"{k}: atributo desconhecido em {type_}")
            continue
        if v is None:
            errors.append(f"{k}: valor nulo")
            continue
        converted = attr_to_ngsi(attr, v, errors)
        if converted is not None:
            out[k] = converted
    if errors:
        raise ConversionError(errors)
    return out


def from_ngsi(entity: dict) -> dict:
    type_ = entity["type"]
    attrs = {a["name"]: a for a in ENTITIES.get(type_, {"attrs": []})["attrs"]}
    out = {"id": slug_of(type_, entity["id"]) or entity["id"]}
    for k, v in entity.items():
        if k in ("id", "type", "@context") or not isinstance(v, dict):
            continue
        attr = attrs.get(k)
        if v.get("type") == "Relationship":
            o = v.get("object")
            candidates = targets(attr) if attr else []
            slug = slug_of(candidates[0], o) if len(candidates) == 1 else None
            out[k] = slug if slug is not None else o
        elif v.get("type") == "GeoProperty":
            out[k] = v.get("value", {}).get("coordinates")
        else:
            value = v.get("value")
            if isinstance(value, dict) and "@value" in value:
                value = value["@value"]
            subs = {s: v[s]["value"] for s in (attr or {}).get("subattrs", {}) if isinstance(v.get(s), dict)}
            if subs or "observedAt" in v:
                out[k] = {"value": value, **subs, **({"observedAt": v["observedAt"]} if "observedAt" in v else {})}
            else:
                out[k] = value
    return out
