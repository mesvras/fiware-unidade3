from spec import ENTITIES

NUMERIC = {"integer", "number"}


def _value_schema(a: dict) -> dict:
    t = a["vtype"]
    if a["kind"] == "R":
        return {"type": "string", "description": f"Identificador de {a['target']}"}
    if a["kind"] == "G":
        return {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3, "description": "[longitude, latitude]"}
    if t in NUMERIC:
        s = {"type": t}
        s.update({k: a[k] for k in ("minimum", "maximum") if k in a})
    elif t == "string":
        s = {"type": "string"}
        s.update({k: a[k] for k in ("pattern", "minLength", "maxLength") if k in a})
    elif t == "boolean":
        s = {"type": "boolean"}
    elif t == "enum":
        s = {"type": "string", "enum": a["enum"]}
    elif t == "arrayenum":
        s = {"type": "array", "items": {"type": "string", "enum": a["enum"]}}
    elif t == "array":
        s = {"type": "array", "items": {"type": a.get("items", "string")}}
    elif t == "datetime":
        s = {"type": "string", "format": "date-time", "example": "2026-12-20T22:00:00Z"}
    elif t == "date":
        s = {"type": "string", "format": "date"}
    else:
        s = {"type": "array" if a.get("array") else "object"}
    if a.get("subattrs"):
        props = {"value": s, **{k: {"type": "string", "pattern": v["pattern"]} for k, v in a["subattrs"].items()}}
        return {"type": "object", "properties": props, "required": ["value", *a["subattrs"]]}
    if a.get("observed_at"):
        return {"oneOf": [s, {"type": "object", "properties": {"value": s, "observedAt": {"type": "string", "format": "date-time"}}, "required": ["value"]}]}
    return s


def body_schema(type_: str, exclude: tuple[str, ...] = (), extra: dict | None = None, partial: bool = False, with_id: bool = True) -> dict:
    attrs = [a for a in ENTITIES[type_]["attrs"] if a["name"] not in exclude and a["name"] != "dataOwner"]
    props = {a["name"]: {**_value_schema(a), "description": a["desc"]} for a in attrs}
    required = [a["name"] for a in attrs if a["req"] == "R"]
    if with_id:
        props = {"id": {"type": "string", "pattern": "^[A-Za-z0-9._-]+$"}, **props}
        required = ["id", *required]
    props.update(extra or {})
    schema = {"type": "object", "properties": props, "additionalProperties": False}
    if not partial:
        schema["required"] = required + [k for k in (extra or {}) if k not in required]
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}}
