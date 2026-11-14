"""Valida os exemplos: (1) JSON Schema, (2) expansão JSON-LD offline, (3) regras semânticas, (4) integridade referencial,
(5) casos inválidos que precisam falhar."""
import json, os, re, sys, copy, glob
from pyld import jsonld
sys.path.insert(0, os.path.dirname(__file__))
from spec import *
from checks import schema_check, rules, entity_integrity
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_URL = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
LOCAL = {CTX_URL: "natal-context.jsonld", SDM_CTX: "ctx/sdm-merged-offline.jsonld", CORE_URL: "ctx/ngsi-ld-core-context.jsonld"}
def loader(url, options=None):
    if url not in LOCAL: raise jsonld.JsonLdError("contexto remoto não mapeado offline: "+url, "loading document failed")
    return {"contentType":"application/ld+json","contextUrl":None,"documentUrl":url,"document":json.load(open(os.path.join(ROOT,LOCAL[url])))}
jsonld.set_document_loader(loader)
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

def integrity(all_):
    byid = {e["id"]: e for e in all_}
    return [x for e in all_ for x in entity_integrity(e, byid)]

def check_entity(e, all_):
    return schema_check(e) + expand_check(e) + rules(e, {x["id"]: x for x in all_})

def vocab_check():
    errs = []
    voc = json.load(open(os.path.join(ROOT,"natal-vocab.jsonld")))
    ctx = json.load(open(os.path.join(ROOT,"natal-context.jsonld")))["@context"][1]
    for n in jsonld.expand(voc):
        i = n["@id"]; kinds = [k.rsplit("#",1)[1] for k in n if k.startswith("http://www.w3.org/2000/01/rdf-schema#sub")]
        term = i[len(NS):]
        if term not in SCHEMA_MAP: errs.append("vocabulário tem termo fora do mapa: "+term); continue
        rel, target = SCHEMA_MAP[term]
        if kinds != [rel]: errs.append("%s: relação %s, esperado %s" % (term, kinds, rel))
        elif n["http://www.w3.org/2000/01/rdf-schema#"+rel][0]["@id"] != target: errs.append("%s: alvo diferente de %s" % (term, target))
        if ctx.get(term, {}).get("@id") != i: errs.append("%s: IRI do contexto difere do vocabulário" % term)
    seen = {n["@id"][len(NS):] for n in jsonld.expand(voc)}
    for term in SCHEMA_MAP:
        if term not in seen: errs.append("termo do mapa ausente no vocabulário: "+term)
    return errs

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
    ve = vocab_check()
    print("== Vocabulário schema.org: %s" % ("OK" if not ve else "FALHA"))
    for x in ve: print("   - " + x)
    fails += bool(ve)
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
    case("data-com-fracao-de-segundo", "urn:ngsi-ld:Event:show-bar-modelo-20261220", lambda e: e["startDate"]["value"].update({"@value":"2026-12-20T22:00:00.500Z"}), "startDate")
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
