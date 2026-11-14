"""Valida os exemplos: (1) JSON Schema, (2) expansão JSON-LD offline, (3) regras semânticas, (4) integridade referencial,
(5) casos inválidos que precisam falhar."""
import json, os, re, sys, copy, glob
import jsonschema
from pyld import jsonld
sys.path.insert(0, os.path.dirname(__file__))
from spec import *
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_URL = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
LOCAL = {CTX_URL: "natal-context.jsonld", SDM_CTX: "ctx/sdm-merged-offline.jsonld", CORE_URL: "ctx/ngsi-ld-core-context.jsonld"}
def loader(url, options=None):
    if url not in LOCAL: raise jsonld.JsonLdError("contexto remoto não mapeado offline: "+url, "loading document failed")
    return {"contentType":"application/ld+json","contextUrl":None,"documentUrl":url,"document":json.load(open(os.path.join(ROOT,LOCAL[url])))}
jsonld.set_document_loader(loader)
SCHEMAS = {n: json.load(open(os.path.join(ROOT,"schemas",n+".schema.json"))) for n in ENTITIES}
KEYWORDS = {"@context","id","type","value","object","observedAt","unitCode","datasetId","@type","@value"}

def terms():
    t = set()
    for u in (CTX_URL, SDM_CTX, CORE_URL):
        c = loader(u)["document"]["@context"]
        for x in (c if isinstance(c, list) else [c]):
            if isinstance(x, dict): t |= set(x)
    return t
TERMS = terms()

def undefined_terms(node, path="", found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            if k in KEYWORDS or k.startswith("@"): pass
            elif k not in TERMS and k not in ("Point","coordinates"): found.append(path+"/"+k)
            undefined_terms(v, path+"/"+k, found)
    elif isinstance(node, list):
        for v in node: undefined_terms(v, path, found)
    return found

def expand_check(e):
    errs = []
    doc = copy.deepcopy(e); ctx = doc.pop("@context"); ctx = ctx if isinstance(ctx, list) else [ctx]
    doc["@context"] = ctx + [CORE_URL]
    try: x = jsonld.expand(doc)
    except Exception as ex: return ["expansão JSON-LD falhou: %s" % str(ex)[:150]]
    if len(x) != 1: return ["expansão produziu %d nós" % len(x)]
    n_in = len([k for k in e if k not in ("@context","id","type")])
    n_out = len([k for k in x[0] if not k.startswith("@")])
    if n_in != n_out: errs.append("atributos perdidos na expansão: %d entrada, %d saída" % (n_in, n_out))
    for u in undefined_terms({k:v for k,v in e.items() if k!="@context"}): errs.append("termo sem definição no contexto: "+u)
    return errs

def schema_check(e):
    s = SCHEMAS.get(e.get("type"))
    if not s: return ["tipo desconhecido: %s" % e.get("type")]
    v = jsonschema.Draft202012Validator(s)
    return ["schema: %s: %s" % ("/".join(map(str,x.absolute_path)) or "(raiz)", x.message[:140]) for x in sorted(v.iter_errors(e), key=lambda x: list(map(str,x.absolute_path)))]

def val(e, a): return e.get(a, {}).get("value")
def dt(e, a):
    v = val(e, a); return v["@value"] if isinstance(v, dict) else None
def obj(e, a): return e.get(a, {}).get("object")

def rules(e, all_):
    t = e["type"]; errs = []; byid = {x["id"]: x for x in all_}
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

def integrity(all_):
    ids = {e["id"]: e for e in all_}; errs = []
    for e in all_:
        for k, v in e.items():
            if isinstance(v, dict) and v.get("type") == "Relationship":
                tgt = ids.get(v["object"])
                if not tgt: errs.append("%s.%s aponta para entidade inexistente %s" % (e["id"], k, v["object"]))
        for a in ENTITIES[e["type"]]["attrs"]:
            if a["kind"] == "R" and a["name"] in e and "object" in e[a["name"]]:
                tgt = ids.get(e[a["name"]]["object"])
                if tgt and tgt["type"] not in re.findall(r"\b(%s)\b" % "|".join(ENTITIES), a["target"]): errs.append("%s.%s aponta para tipo %s, esperado %s" % (e["id"], a["name"], tgt["type"], a["target"]))
    return errs

def check_entity(e, all_):
    return schema_check(e) + expand_check(e) + rules(e, all_)

def run():
    ents = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ROOT,"examples","*.jsonld")))]
    fails = 0
    print("== Exemplos válidos (%d)" % len(ents))
    for e in ents:
        errs = check_entity(e, ents)
        print(("  OK    " if not errs else "  FALHA ") + e["id"])
        for x in errs: print("        - " + x)
        fails += bool(errs)
    ie = integrity(ents)
    print("== Integridade referencial: %s" % ("OK" if not ie else "FALHA"))
    for x in ie: print("   - " + x)
    fails += bool(ie)
    return ents, fails

def mutate(ents):
    by = {e["id"]: copy.deepcopy(e) for e in ents}
    g = lambda i: copy.deepcopy(by[i])
    cases = []
    def case(name, base_id, fn, expect):
        e = g(base_id); out = fn(e); cases.append((name, out if out is not None else e, expect))
    case("sem-dataOwner", "urn:ngsi-ld:Hotel:hotel-modelo-farol", lambda e: e.pop("dataOwner") and None, "dataOwner")
    case("enum-invalido", "urn:ngsi-ld:Hotel:hotel-modelo-farol", lambda e: e["category"].update(value="castelo"), "schema")
    case("estrelas-fora-da-faixa", "urn:ngsi-ld:Hotel:hotel-modelo-farol", lambda e: e["starRating"].update(value=7), "starRating")
    case("atributo-com-erro-de-digitacao", "urn:ngsi-ld:Hotel:hotel-modelo-farol", lambda e: e.update(starRatin=e.pop("starRating")), "starRatin")
    case("preco-sem-currency", "urn:ngsi-ld:RoomAvailability:hotel-modelo-farol:standard:20261220", lambda e: e["pricePerNight"].pop("currency") and None, "currency")
    case("disponibilidade-maior-que-total", "urn:ngsi-ld:RoomAvailability:hotel-modelo-farol:standard:20261220", lambda e: e["availableUnits"].update(value=99), "totalUnits")
    case("data-do-id-diferente", "urn:ngsi-ld:RoomAvailability:hotel-modelo-farol:standard:20261220", lambda e: e["stayDate"]["value"].update({"@value":"2026-12-25"}), "stayDate")
    case("data-sem-tipo", "urn:ngsi-ld:RoomAvailability:hotel-modelo-farol:standard:20261220", lambda e: e["stayDate"].update(value="2026-12-20"), "schema")
    case("ocupacao-sem-observedAt", "urn:ngsi-ld:PointOfInterest:restaurante-modelo-mare", lambda e: e["occupancy"].pop("observedAt") and None, "observedAt")
    case("ocupacao-maior-que-capacidade", "urn:ngsi-ld:PointOfInterest:restaurante-modelo-mare", lambda e: e["occupancy"].update(value=200), "occupancy")
    case("evento-termina-antes-de-comecar", "urn:ngsi-ld:Event:show-bar-modelo-20261220", lambda e: e["endDate"]["value"].update({"@value":"2026-12-20T20:00:00Z"}), "endDate")
    case("evento-sem-porte", "urn:ngsi-ld:Event:show-bar-modelo-20261220", lambda e: e.pop("eventScale") and None, "eventScale")
    case("restricao-sem-praia", "urn:ngsi-ld:Event:restricao-banho-praia-modelo-20261224", lambda e: e.pop("refPointOfInterest") and None, "refPointOfInterest")
    case("restricao-aponta-hotel", "urn:ngsi-ld:Event:restricao-banho-praia-modelo-20261224", lambda e: e["refPointOfInterest"].update(object="urn:ngsi-ld:Hotel:hotel-modelo-farol"), "refPointOfInterest")
    case("relacionamento-como-propriedade", "urn:ngsi-ld:RoomType:hotel-modelo-farol:standard", lambda e: e.update(refHotel={"type":"Property","value":"urn:ngsi-ld:Hotel:hotel-modelo-farol"}), "schema")
    case("coordenadas-invertidas-tipo", "urn:ngsi-ld:Beach:praia-modelo-do-farol", lambda e: e["location"]["value"].update(type="Polygon"), "location")
    case("ponto-de-coleta-sem-praia", "urn:ngsi-ld:PointOfInterest:coleta-modelo-farol-01", lambda e: e.pop("refBeach") and None, "refBeach")
    case("pH-fora-da-faixa", "urn:ngsi-ld:WaterQualityObserved:coleta-modelo-farol-01:20261220T120000Z", lambda e: e["pH"].update(value=15), "pH")
    case("sonda-sem-turbidez", "urn:ngsi-ld:WaterQualityObserved:coleta-modelo-farol-01:20261220T120000Z", lambda e: e.pop("turbidity") and None, "turbidity")
    case("chuva-negativa", "urn:ngsi-ld:WeatherObserved:estacao-modelo-01:20261220T120000Z", lambda e: e["precipitation"].update(value=-1), "precipitation")
    case("chuva-sem-intervalo", "urn:ngsi-ld:WeatherObserved:estacao-modelo-01:20261220T120000Z", lambda e: e.pop("precipitationIntervalMinutes") and None, "precipitationIntervalMinutes")
    case("laudo-validade-invertida", "urn:ngsi-ld:BathingReport:praia-modelo-do-farol:laudo-2026-0451", lambda e: e["validUntil"]["value"].update({"@value":"2026-12-10T00:00:00Z"}), "validFrom")
    case("estado-por-laudo-sem-laudo", "urn:ngsi-ld:BathingStatus:praia-modelo-do-farol", lambda e: e.pop("refBathingReport") and None, "refBathingReport")
    case("estado-diverge-do-laudo", "urn:ngsi-ld:BathingStatus:praia-modelo-do-farol", lambda e: e["status"].update(value="improper"), "result")
    case("estado-sem-base-mas-proprio", "urn:ngsi-ld:BathingStatus:praia-modelo-do-farol", lambda e: (e["basis"].update(value="none"), e.pop("refBathingReport")) and None, "indeterminate")
    case("estimativa-sem-risco", "urn:ngsi-ld:BathingStatus:praia-modelo-do-farol", lambda e: (e["basis"].update(value="estimate"), e.pop("refBathingReport")) and None, "estimatedRiskLevel")
    case("restaurante-sem-capacidade", "urn:ngsi-ld:PointOfInterest:restaurante-modelo-mare", lambda e: e.pop("capacity") and None, "capacity")
    case("ponto-de-coleta-com-ocupacao", "urn:ngsi-ld:PointOfInterest:coleta-modelo-farol-01", lambda e: e.update(occupancy={"type":"Property","value":5,"observedAt":"2026-12-20T19:30:00Z"}), "occupancy")
    case("id-com-prefixo-errado", "urn:ngsi-ld:Hotel:hotel-modelo-farol", lambda e: e.update(id="urn:ngsi-ld:RoomType:x"), "schema")
    return cases

def run_invalid(ents):
    os.makedirs(os.path.join(ROOT,"invalid"), exist_ok=True)
    for f in glob.glob(os.path.join(ROOT,"invalid","*.jsonld")): os.remove(f)
    cases = mutate(ents); bad = 0; manifest = {}
    print("== Casos inválidos (%d): cada um precisa falhar com o motivo esperado" % len(cases))
    for name, e, expect in cases:
        pool = [x for x in ents if x["id"] != e["id"]] + [e]
        errs = check_entity(e, pool) + [x for x in integrity(pool) if e["id"] in x]
        hit = any(expect in x for x in errs)
        print(("  OK    " if hit else "  ERRO  ") + name + ("" if hit else "  <- não falhou como esperado: %s" % errs[:2]))
        bad += (not hit)
        json.dump(e, open(os.path.join(ROOT,"invalid",name+".jsonld"),"w"), indent=2, ensure_ascii=False)
        manifest[name] = {"deve_falhar_com": expect, "erros_obtidos": errs[:3]}
    json.dump(manifest, open(os.path.join(ROOT,"invalid","_esperado.json"),"w"), indent=2, ensure_ascii=False)
    return bad

if __name__ == "__main__":
    ents, f1 = run(); f2 = run_invalid(ents)
    print("\nRESULTADO: %s" % ("TUDO OK" if not (f1 or f2) else "%d falha(s) nos válidos, %d caso(s) inválido(s) sem falhar" % (f1, f2)))
    sys.exit(1 if (f1 or f2) else 0)
