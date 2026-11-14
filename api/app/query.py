import json

from .errors import ApiError


def literal(value) -> str:
    return json.dumps(value) if isinstance(value, str) else str(value)


def eq(attr: str, value) -> str:
    return f"{attr}=={literal(value)}"


def date_range(attr: str, start: str | None, end: str | None) -> list[str]:
    terms = []
    if start:
        terms.append(f"{attr}[@value]>={literal(start)}")
    if end:
        terms.append(f"{attr}[@value]<{literal(end)}")
    return terms


def params(type_: str, terms: list[str], limit: int, offset: int, near: str | None = None, max_distance: int | None = None) -> dict:
    p = {"type": type_, "limit": limit, "offset": offset}
    if terms:
        p["q"] = ";".join(terms)
    if near:
        try:
            lon, lat = (float(x) for x in near.split(","))
        except ValueError:
            raise ApiError(400, "near: esperado longitude,latitude")
        p.update({"georel": f"near;maxDistance=={max_distance or 1000}", "geometry": "Point", "coordinates": f"[{lon},{lat}]"})
    return p
