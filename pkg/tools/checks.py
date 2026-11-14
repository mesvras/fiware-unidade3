"""Verificações compartilhadas por validate.py e pela API: JSON Schema, regras semânticas e integridade referencial."""
import json, os, re
import jsonschema
from spec import ENTITIES
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMAS = {n: json.load(open(os.path.join(ROOT,"schemas",n+".schema.json"))) for n in ENTITIES}
VALIDATORS = {n: jsonschema.Draft202012Validator(s) for n, s in SCHEMAS.items()}

def schema_check(e):
    v = VALIDATORS.get(e.get("type"))
    if not v: return ["tipo desconhecido: %s" % e.get("type")]
    return ["schema: %s: %s" % ("/".join(map(str,x.absolute_path)) or "(raiz)", x.message[:140]) for x in sorted(v.iter_errors(e), key=lambda x: list(map(str,x.absolute_path)))]

def val(e, a): return e.get(a, {}).get("value")
def dt(e, a):
    v = val(e, a); return v["@value"] if isinstance(v, dict) else None
def obj(e, a): return e.get(a, {}).get("object")

def rules(e, byid):
    t = e["type"]; errs = []
    cats = val(e, "category") or []
    if t == "Event":
        if dt(e,"endDate") and dt(e,"startDate") and dt(e,"endDate") <= dt(e,"startDate"): errs.append("regra: endDate deve ser posterior a startDate")
        if "bathingRestriction" in cats:
            tgt = obj(e,"refPointOfInterest")
            if not tgt: errs.append("regra: restrição de banho exige refPointOfInterest")
            elif not tgt.startswith("urn:ngsi-ld:Beach:"): errs.append("regra: refPointOfInterest da restrição deve ser uma Beach")
        else:
            if "eventScale" not in e: errs.append("regra: eventScale obrigatório fora de restrição de banho")
    if t == "PointOfInterest":
        if "bathingSamplingPoint" in cats and "refBeach" not in e: errs.append("regra: ponto de coleta exige refBeach")
        food = bool({"restaurant","bar"} & set(cats))
        for a in ("address","capacity","occupancy"):
            if food and a not in e: errs.append("regra: restaurante ou bar exige %s" % a)
        if not food:
            for a in ("capacity","occupancy","availabilityLevel","cuisine","priceRange","openingHoursSpecification"):
                if a in e: errs.append("regra: %s só vale para restaurante ou bar" % a)
        if val(e,"occupancy") is not None and val(e,"capacity") is not None and val(e,"occupancy") > val(e,"capacity"): errs.append("regra: occupancy maior que capacity")
    if t == "RoomAvailability":
        m = re.match(r"urn:ngsi-ld:RoomAvailability:[^:]+:[^:]+:(\d{8})$", e["id"])
        d = dt(e,"stayDate")
        if not m: errs.append("regra: id de RoomAvailability fora do padrão hotel:tipo:AAAAMMDD")
        elif d and m.group(1) != d.replace("-",""): errs.append("regra: data do id difere de stayDate")
        rt = byid.get(obj(e,"refRoomType"))
        if rt:
            if val(e,"availableUnits") is not None and val(e,"availableUnits") > val(rt,"totalUnits"): errs.append("regra: availableUnits maior que totalUnits do RoomType")
            if obj(e,"refHotel") != obj(rt,"refHotel"): errs.append("regra: refHotel difere do refHotel do RoomType")
    if t == "BathingReport":
        a, b, c = dt(e,"collectionDate"), dt(e,"validFrom"), dt(e,"validUntil")
        if a and b and a > b: errs.append("regra: collectionDate posterior a validFrom")
        if b and c and b >= c: errs.append("regra: validFrom deve ser anterior a validUntil")
    if t == "BathingStatus":
        basis, status = val(e,"basis"), val(e,"status")
        if basis != "none" and "validUntil" not in e: errs.append("regra: validUntil obrigatório quando basis != none")
        if basis == "report":
            if "refBathingReport" not in e: errs.append("regra: basis=report exige refBathingReport")
            else:
                r = byid.get(obj(e,"refBathingReport"))
                if r and val(r,"result") != status: errs.append("regra: status difere do result do laudo")
        if basis == "estimate" and "estimatedRiskLevel" not in e: errs.append("regra: basis=estimate exige estimatedRiskLevel")
        if basis == "none" and status != "indeterminate": errs.append("regra: basis=none exige status=indeterminate")
    return errs

def relationship_targets(e):
    return [v["object"] for v in e.values() if isinstance(v, dict) and v.get("type") == "Relationship" and "object" in v]

def entity_integrity(e, byid):
    errs = []
    for k, v in e.items():
        if isinstance(v, dict) and v.get("type") == "Relationship" and "object" in v:
            if v["object"] not in byid: errs.append("%s.%s aponta para entidade inexistente %s" % (e["id"], k, v["object"]))
    for a in ENTITIES.get(e.get("type"), {"attrs": []})["attrs"]:
        if a["kind"] == "R" and isinstance(e.get(a["name"]), dict) and "object" in e[a["name"]]:
            tgt = byid.get(e[a["name"]]["object"])
            if tgt and tgt["type"] not in re.findall(r"\b(%s)\b" % "|".join(ENTITIES), a["target"]): errs.append("%s.%s aponta para tipo %s, esperado %s" % (e["id"], a["name"], tgt["type"], a["target"]))
    return errs

def check(e, byid):
    errs = schema_check(e)
    if errs and any("tipo desconhecido" in x for x in errs): return errs
    return errs + rules(e, byid) + entity_integrity(e, byid)

