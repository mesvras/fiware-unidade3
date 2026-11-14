import json, re, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from spec import *
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DT = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
D  = r"^\d{4}-\d{2}-\d{2}$"
KNOWN = list(ENTITIES)

def typed(t, pat):
    return {"type":"object","required":["@type","@value"],"additionalProperties":False,
            "properties":{"@type":{"const":t},"@value":{"type":"string","pattern":pat}}}

def vschema(a):
    t = a["vtype"]; s = {}
    if t == "string":
        s = {"type":"string"}
        for k in ("pattern","minLength","maxLength"):
            if k in a: s[k] = a[k]
    elif t in ("integer","number"):
        s = {"type":t}
        for k in ("minimum","maximum"):
            if k in a: s[k] = a[k]
    elif t == "boolean": s = {"type":"boolean"}
    elif t == "enum": s = {"enum":a["enum"]}
    elif t == "arrayenum":
        s = {"type":"array","items":{"enum":a["enum"]},"uniqueItems":True}
        for k in ("minItems","maxItems"):
            if k in a: s[k] = a[k]
    elif t == "array": s = {"type":"array","items":{"type":a.get("items","string")}}
    elif t == "datetime": s = typed("DateTime", DT)
    elif t == "date": s = typed("Date", D)
    elif t == "point":
        s = {"type":"object","required":["type","coordinates"],"additionalProperties":False,
             "properties":{"type":{"const":"Point"},"coordinates":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":3}}}
    elif t == "object":
        ks = a.get("keys", [])
        o = {"type":"object","properties":{k:{"type":"string"} for k in ks},"additionalProperties":False}
        if a.get("required_keys"): o["required"] = a["required_keys"]
        if a.get("array"):
            o = {"type":"object","properties":{"dayOfWeek":{"type":"array","items":{"type":"string"}},"opens":{"type":"string","pattern":r"^\d{2}:\d{2}(:\d{2})?$"},"closes":{"type":"string","pattern":r"^\d{2}:\d{2}(:\d{2})?$"}},"required":["opens","closes"],"additionalProperties":False}
            s = {"type":"array","items":o}
        else: s = o
    return s

def attr_schema(a):
    if a["kind"] == "R":
        targets = [n for n in KNOWN if re.search(r"\b%s\b" % n, a["target"])]
        pat = "^urn:ngsi-ld:(%s):[A-Za-z0-9._:-]+$" % "|".join(targets)
        return {"type":"object","required":["type","object"],"additionalProperties":False,
                "properties":{"type":{"const":"Relationship"},"object":{"type":"string","pattern":pat},
                              "observedAt":{"type":"string","pattern":DT}}}
    props = {"type":{"const":"GeoProperty" if a["kind"]=="G" else "Property"}, "value":vschema(a),
             "observedAt":{"type":"string","pattern":DT}}
    req = ["type","value"]
    if a.get("observed_at"): req.append("observedAt")
    for sk, sv in a.get("subattrs", {}).items():
        props[sk] = {"type":"object","required":["type","value"],"additionalProperties":False,
                     "properties":{"type":{"const":"Property"},"value":{"type":"string","pattern":sv["pattern"]}}}
        if sv.get("required"): req.append(sk)
    return {"type":"object","required":req,"additionalProperties":False,"properties":props}

def entity_schema(e):
    props = {"id":{"type":"string","pattern":"^urn:ngsi-ld:%s:[A-Za-z0-9._:-]+$" % e["name"]},
             "type":{"const":e["name"]},
             "@context":{"anyOf":[{"type":"string"},{"type":"array","items":{"type":["string","object"]}}]}}
    req = ["id","type"]
    for a in e["attrs"]:
        props[a["name"]] = attr_schema(a)
        if a["req"] == "R": req.append(a["name"])
    return {"$schema":"https://json-schema.org/draft/2020-12/schema",
            "$id":"%sschemas/%s.schema.json" % (CTX_URL.rsplit("/",1)[0]+"/", e["name"]),
            "title":e["name"],"description":e["desc"],"type":"object","required":req,
            "properties":props,"additionalProperties":False}

def build_context():
    c = {"natal": NS}
    for n in CUSTOM_TYPES: c[n] = {"@id": NS+n}
    seen = set()
    for e in ENTITIES.values():
        for a in e["attrs"]:
            if a["origem"] == "EXT" and a["name"] not in seen:
                seen.add(a["name"]); c[a["name"]] = {"@id": NS+a["name"]}
            for sk in a.get("subattrs", {}):
                if sk not in seen: seen.add(sk); c[sk] = {"@id": NS+sk}
    # termos ambíguos entre domínios SDM: fixa um único IRI
    c["category"] = {"@id":"https://smartdatamodels.org/dataModel.TourismDestinations/category"}
    c["refPointOfInterest"] = {"@id":"https://smartdatamodels.org/dataModel.TourismDestinations/refPointOfInterest"}
    for t in ["Beach","PointOfInterest","Event","WaterQualityObserved","WeatherObserved"]:
        pass
    extra = json.load(open(os.path.join(ROOT,"tools","extra_terms.json"))) if os.path.exists(os.path.join(ROOT,"tools","extra_terms.json")) else {}
    c.update(extra)
    return {"@context":[SDM_CTX, c]}

def build_vocab():
    graph = []
    for term, (rel, target) in SCHEMA_MAP.items():
        is_class = term in ENTITIES
        graph.append({"@id": NS+term, "@type": "rdfs:Class" if is_class else "rdf:Property",
                      "rdfs:"+rel: {"@id": target}})
    return {"@context": {"rdf":"http://www.w3.org/1999/02/22-rdf-syntax-ns#","rdfs":"http://www.w3.org/2000/01/rdf-schema#"}, "@graph": graph}

def pad_table(rows):
    w = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out = []
    for k, r in enumerate(rows):
        out.append("  ".join(r[i].ljust(w[i]) for i in range(len(r))).rstrip())
        if k == 0: out.append("  ".join("-"*w[i] for i in range(len(r))))
    return "```\n" + "\n".join(out) + "\n```"

KIND = {"P":"Property","G":"GeoProperty","R":"Relationship"}
def dtype(a):
    t = a["vtype"]
    if t == "uri": return "URI → " + a["target"]
    if t == "enum": return "enum(" + ", ".join(a["enum"]) + ")"
    if t == "arrayenum": return "lista de enum"
    m = {"datetime":"DateTime","date":"Date","point":"GeoJSON Point","object":"objeto","array":"lista de texto","string":"texto","integer":"inteiro","number":"número","boolean":"booleano"}
    s = m[t]
    if "minimum" in a or "maximum" in a: s += " [%s..%s]" % (a.get("minimum",""), a.get("maximum",""))
    return s
def req(a): return "Sim" if a["req"]=="R" else ("Não" if a["req"]=="O" else "Cond.")

def build_docs():
    md = []
    for e in ENTITIES.values():
        md.append(f"### {e['name']}\n")
        md.append(f"{e['desc']}\n")
        md.append(f"- Origem: {e['origem']}")
        md.append(f"- Id: `{e['idpat']}`\n")
        rows = [["Atributo","Tipo NGSI-LD","Tipo de dado","Obrig.","Origem"]]
        for a in e["attrs"]:
            rows.append([a["name"],KIND[a["kind"]],dtype(a),req(a),a["origem"]])
        md.append(pad_table(rows) + "\n")
        notes = []
        for a in e["attrs"]:
            if a["req"].startswith("C:"): notes.append(f"- `{a['name']}`: obrigatório {a['req'][2:].replace('R, exceto','exceto').replace('R se','se')}.")
            if a.get("subattrs"): notes.append(f"- `{a['name']}` exige sub-atributo `currency` (ISO 4217, ex.: BRL).")
            if a.get("observed_at"): notes.append(f"- `{a['name']}` exige `observedAt` no atributo.")
        notes += [f"- Regra: {r}." for r in e["rules"]]
        if notes: md.append("\n".join(notes) + "\n")
        md.append("Descrições dos atributos:\n")
        for a in e["attrs"]: md.append(f"- `{a['name']}`: {a['desc']}")
        md.append("")
    md.append("## Alinhamento com schema.org\n")
    md.append("O arquivo `natal-vocab.jsonld` declara que termos do projeto são especializações de termos do schema.org. O `@context` não muda: os termos continuam com IRI próprio. Só entram os termos de significado equivalente.\n")
    rows = [["Termo do projeto","Relação","Termo do schema.org"]]
    for term, (rel, target) in SCHEMA_MAP.items(): rows.append([term, "rdfs:"+rel, target])
    md.append(pad_table(rows) + "\n")
    return "\n".join(md)

if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT,"schemas"), exist_ok=True)
    for e in ENTITIES.values():
        json.dump(entity_schema(e), open(os.path.join(ROOT,"schemas",e["name"]+".schema.json"),"w"), indent=2, ensure_ascii=False)
    json.dump(build_context(), open(os.path.join(ROOT,"natal-context.jsonld"),"w"), indent=2, ensure_ascii=False)
    json.dump(build_vocab(), open(os.path.join(ROOT,"natal-vocab.jsonld"),"w"), indent=2, ensure_ascii=False)
    open(os.path.join(ROOT,"docs","modelos.md"),"w").write(build_docs())
    print("ok", len(ENTITIES), "entidades")
