#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

TENANT=smoketest
CTX=http://context/natal-context.jsonld
LINK="Link: <$CTX>; rel=\"http://www.w3.org/ns/json-ld#context\"; type=\"application/ld+json\""
WORK=$(mktemp -d)
FAILS=0

ok() { echo "  OK    $1"; }
fail() { echo "  FALHA $1${2:+: $2}"; FAILS=$((FAILS + 1)); }
expect() { if [ "$2" = "$3" ]; then ok "$1"; else fail "$1" "esperado $3, obtido $2"; fi; }

orion() { docker compose exec -T orion curl -sS -m 20 -H "NGSILD-Tenant: $TENANT" "$@"; }
api() { local method=$1 path=$2; shift 2; docker compose exec -T orion curl -sS -m 20 -X "$method" -H 'Content-Type: application/json' "$@" "http://api:8000$path" < /dev/null; }
status() { api "$@" -o /dev/null -w '%{http_code}'; }
ql() { docker compose exec -T quantumleap curl -sS -m 20 -H "Fiware-Service: $TENANT" "$@"; }
sql() { docker compose exec -T crate curl -sS -m 20 -X POST http://localhost:4200/_sql -H 'Content-Type: application/json' -d "{\"stmt\":\"$1\"}"; }
iota() {
  docker compose exec -T iot-agent node -e '
    const [t, m, u, b] = process.argv.slice(1);
    const r = require("http").request(u, {method: m, headers: {"Content-Type": "application/json", "fiware-service": t, "fiware-servicepath": "/"}},
      s => { s.resume(); s.on("end", () => console.log(s.statusCode)); });
    r.on("error", () => console.log(0)); if (b) r.write(b); r.end();' "$TENANT" "$@"
}
json() { python3 -I -c "import sys, json; d = json.load(sys.stdin); print($1)"; }

cleanup() {
  iota DELETE http://localhost:4041/iot/devices/smoke001 >/dev/null 2>&1
  iota DELETE "http://localhost:4041/iot/services?resource=/iot/json&apikey=smokekey" >/dev/null 2>&1
  orion -X DELETE http://localhost:1026/ngsi-ld/v1/subscriptions/urn:ngsi-ld:Subscription:smoke-ql -o /dev/null 2>/dev/null
  sql "drop table if exists mt$TENANT.etsmokeseries" >/dev/null 2>&1
  sql "delete from doc.md_ets_metadata where table_name like '%mt$TENANT%'" >/dev/null 2>&1
  local types ids
  types="SmokeDevice SmokeSeries SmokeConcurrency $(docker compose exec -T orion curl -sS -m 20 http://context/examples-batch.jsonld | json '" ".join(sorted({e["type"] for e in d}))' 2>/dev/null)"
  for type in $types; do
    ids=$(orion -G http://localhost:1026/ngsi-ld/v1/entities -H "$LINK" --data-urlencode "type=$type" --data-urlencode limit=1000 | json 'json.dumps([e["id"] for e in d])' 2>/dev/null)
    [ -n "$ids" ] && [ "$ids" != "[]" ] && orion -X POST http://localhost:1026/ngsi-ld/v1/entityOperations/delete -H 'Content-Type: application/json' -d "$ids" -o /dev/null
  done
  for path in /v1/events/smoke-show /v1/restaurants/smoke-rest /v1/bars/smoke-bar \
              /v1/hotels/smoke-hotel/availability/std/2026-12-20 /v1/hotels/smoke-hotel/room-types/std /v1/hotels/smoke-hotel; do
    api DELETE "$path" -o /dev/null 2>/dev/null
  done
  rm -rf "$WORK"
}
trap cleanup EXIT
cleanup; WORK=$(mktemp -d)

echo "== Serviços"
for svc in $(docker compose config --services); do
  expect "$svc healthy" "$(docker compose ps --format '{{.Health}}' "$svc")" "healthy"
done
published=$(docker compose config --format json | json 'sum(1 for s in d["services"].values() if s.get("ports"))')
expect "nenhuma porta publicada" "$published" "0"

echo "== Orion-LD com requisições concorrentes"
restarts() { docker inspect "$(docker compose ps -q orion)" --format '{{.RestartCount}}'; }
before=$(restarts)
codes=$(docker compose exec -T api python -c '
import asyncio, collections, sys, httpx
tenant, entities, total, conns = sys.argv[1], 8, 1000, 8
async def main():
    async with httpx.AsyncClient(base_url="http://orion:1026/ngsi-ld/v1/entities", headers={"NGSILD-Tenant": tenant}, timeout=20) as c:
        for i in range(entities):
            await c.post("", json={"id": f"urn:ngsi-ld:SmokeConcurrency:{i}", "type": "SmokeConcurrency", "n": {"type": "Property", "value": 0}})
        limit, codes = asyncio.Semaphore(conns), collections.Counter()
        async def patch(i):
            async with limit:
                try:
                    r = await c.patch(f"/urn:ngsi-ld:SmokeConcurrency:{i % entities}/attrs", json={"n": {"type": "Property", "value": i}})
                    codes[r.status_code] += 1
                except httpx.HTTPError as e:
                    codes[type(e).__name__] += 1
        await asyncio.gather(*(patch(i) for i in range(total)))
    print(" ".join(f"{k}={v}" for k, v in sorted(codes.items(), key=str)))
asyncio.run(main())' "$TENANT" < /dev/null)
errors=$(echo "$codes" | tr ' ' '\n' | grep -v '^[0-9]' | tr '\n' ' ')
expect "1000 PATCH com 8 conexões sem erros de conexão ($codes)" "${errors:-nenhum}" "nenhum"
expect "Orion-LD sem reinícios" "$(restarts)" "$before"

echo "== MQTT, IoT Agent e Orion-LD"
expect "grupo provisionado" "$(iota POST http://localhost:4041/iot/services '{"services":[{"apikey":"smokekey","cbroker":"http://orion:1026","entity_type":"SmokeDevice","resource":"/iot/json"}]}')" "201"
expect "dispositivo provisionado" "$(iota POST http://localhost:4041/iot/devices '{"devices":[{"device_id":"smoke001","apikey":"smokekey","entity_name":"urn:ngsi-ld:SmokeDevice:001","entity_type":"SmokeDevice","transport":"MQTT","attributes":[{"object_id":"t","name":"temperature","type":"Number"}]}]}')" "201"
docker compose exec -T mosquitto mosquitto_pub -t /smokekey/smoke001/attrs -m '{"t":27.5}'
value=""
for _ in $(seq 10); do
  value=$(orion http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:SmokeDevice:001 | json 'd.get("temperature", {}).get("value", "")' 2>/dev/null)
  [ -n "$value" ] && break; sleep 1
done
expect "medição MQTT chega ao Orion-LD" "$value" "27.5"

echo "== Orion-LD, QuantumLeap e CrateDB"
expect "assinatura criada" "$(orion -X POST http://localhost:1026/ngsi-ld/v1/subscriptions -H 'Content-Type: application/json' -o /dev/null -w '%{http_code}' \
  -d '{"id":"urn:ngsi-ld:Subscription:smoke-ql","type":"Subscription","entities":[{"type":"SmokeSeries"}],"notification":{"format":"normalized","endpoint":{"uri":"http://quantumleap:8668/v2/notify","accept":"application/json"}}}')" "201"
orion -X POST http://localhost:1026/ngsi-ld/v1/entities -H 'Content-Type: application/json' -o /dev/null \
  -d '{"id":"urn:ngsi-ld:SmokeSeries:1","type":"SmokeSeries","temperature":{"type":"Property","value":25.5}}'
sleep 2
orion -X PATCH http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:SmokeSeries:1/attrs -H 'Content-Type: application/json' -o /dev/null \
  -d '{"temperature":{"type":"Property","value":26.5}}'
series=""
for _ in $(seq 15); do
  series=$(ql http://localhost:8668/v2/entities/urn:ngsi-ld:SmokeSeries:1/attrs/temperature | json 'd.get("values")' 2>/dev/null)
  [ "$series" = "[25.5, 26.5]" ] && break; sleep 1
done
expect "histórico no QuantumLeap" "$series" "[25.5, 26.5]"
orion -X DELETE http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:SmokeSeries:1 -o /dev/null

echo "== API da plataforma"
expect "hotel criado pela API" "$(status POST /v1/hotels -d '{"id":"smoke-hotel","name":"Hotel Smoke","location":[-35.205,-5.87],"address":{"addressLocality":"Natal"}}')" "201"
expect "tipo de quarto criado" "$(status POST /v1/hotels/smoke-hotel/room-types -d '{"id":"std","name":"Std","maxAdults":2,"maxChildren":1,"totalUnits":3}')" "201"
expect "disponibilidade criada" "$(status POST /v1/hotels/smoke-hotel/availability -d '{"roomType":"std","stayDate":"2026-12-20","availableUnits":2,"pricePerNight":{"value":250.0,"currency":"BRL"}}')" "201"
offers=$(api GET "/v1/availability?checkIn=2026-12-20&checkOut=2026-12-21&adults=2" | json '[float(o["totalPrice"]["value"]) for o in d if o["hotel"] == "smoke-hotel"]')
expect "busca por período e grupo" "$offers" "[250.0]"
expect "bar criado" "$(status POST /v1/bars -d '{"id":"smoke-bar","name":"Bar Smoke","location":[-35.2071,-5.8695],"address":{"addressLocality":"Natal"},"capacity":40,"occupancy":35}')" "201"
expect "restaurante criado" "$(status POST /v1/restaurants -d '{"id":"smoke-rest","name":"Rest Smoke","location":[-35.2062,-5.8688],"address":{"addressLocality":"Natal"},"capacity":80,"occupancy":10}')" "201"
expect "evento no bar criado" "$(status POST /v1/events -d '{"id":"smoke-show","name":"Show Smoke","startDate":"2026-12-20T22:00:00Z","endDate":"2026-12-21T00:30:00Z","location":[-35.2071,-5.8695],"address":{"addressLocality":"Natal"},"category":["spectacle"],"eventScale":"small","eventStatus":["scheduled"],"refPointOfInterest":{"bar":"smoke-bar"}}')" "201"
level=$(docker compose exec -T orion curl -sS -m 20 http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:PointOfInterest:smoke-bar -H "$LINK" < /dev/null | json 'd["availabilityLevel"]["value"]')
expect "Orion-LD recebe o que a API grava (availabilityLevel)" "$level" "limited"
agenda=$(api GET "/v1/events?from=2026-12-20&to=2026-12-21&near=-35.2071,-5.8695&maxDistance=500" | json '[e["id"] for e in d if e["id"].startswith("smoke-")]')
expect "agenda por janela e área" "$agenda" "['smoke-show']"
expect "registro referenciado não é removido" "$(status DELETE /v1/bars/smoke-bar)" "409"
for path in /v1/events/smoke-show /v1/restaurants/smoke-rest /v1/bars/smoke-bar /v1/hotels/smoke-hotel/availability/std/2026-12-20 \
            /v1/hotels/smoke-hotel/room-types/std /v1/hotels/smoke-hotel; do
  code=$(status DELETE "$path"); [ "$code" = "204" ] || fail "remoção de $path" "HTTP $code"
done
ok "remoção dos registros da API"

echo "== Exemplos NGSI-LD"
docker compose exec -T orion curl -sS -m 20 http://context/examples-batch.jsonld > "$WORK/batch.json"
total=$(json 'len(d)' < "$WORK/batch.json")
orion -X POST http://localhost:1026/ngsi-ld/v1/entityOperations/upsert -H 'Content-Type: application/ld+json' \
  --data-binary @- -w '\n%{http_code}' < "$WORK/batch.json" > "$WORK/upsert.txt"
code=$(tail -n 1 "$WORK/upsert.txt")
case "$code" in 201|204) ok "upsert em lote dos $total exemplos ($code)";; *) fail "upsert em lote" "HTTP $code: $(head -c 300 "$WORK/upsert.txt")";; esac

for type in $(json '" ".join(sorted({e["type"] for e in d}))' < "$WORK/batch.json"); do
  want=$(json "sum(1 for e in d if e['type'] == '$type')" < "$WORK/batch.json")
  got=$(orion -G http://localhost:1026/ngsi-ld/v1/entities -H "$LINK" --data-urlencode "type=$type" --data-urlencode limit=100 | json 'len(d)')
  expect "contagem de $type" "$got" "$want"
done

python3 -I -c "import json, sys; [print(e['id']) for e in json.load(open(sys.argv[1]))]" "$WORK/batch.json" > "$WORK/ids"
diffs=0
checked=0
while read -r id; do
  orion http://localhost:1026/ngsi-ld/v1/entities/"$id" -H "$LINK" < /dev/null > "$WORK/got.json"
  out=$(python3 -I -c '
import json, sys
from datetime import datetime
def instant(t): return datetime.fromisoformat(t.replace("Z", "+00:00"))
def same(w, g):
    if not (isinstance(w, dict) and isinstance(g, dict)): return w == g
    g = dict(g)
    if isinstance(w.get("value"), list) and len(w["value"]) == 1 and g.get("value") == w["value"][0]: g["value"] = w["value"]
    if "observedAt" in w and "observedAt" in g and instant(w["observedAt"]) == instant(g["observedAt"]): g["observedAt"] = w["observedAt"]
    return w == g
want = next(e for e in json.load(open(sys.argv[1])) if e["id"] == sys.argv[3])
got = json.load(open(sys.argv[2]))
for x in (want, got): x.pop("@context", None)
keys = sorted(set(want) | set(got))
print("; ".join(k for k in keys if not same(want.get(k), got.get(k))))' "$WORK/batch.json" "$WORK/got.json" "$id")
  checked=$((checked + 1))
  if [ -n "$out" ]; then fail "leitura de $id" "atributos diferentes: $out"; diffs=$((diffs + 1)); fi
done < "$WORK/ids"
expect "exemplos comparados na leitura de volta" "$checked" "$total"
[ "$diffs" -eq 0 ] && ok "leitura de volta equivalente nos $total exemplos"

q() { orion -G http://localhost:1026/ngsi-ld/v1/entities -H "$LINK" "$@" | json '" ".join(sorted(e["id"].rsplit(":", 1)[-1] for e in d))'; }
expect "consulta category==restaurant" "$(q --data-urlencode type=PointOfInterest --data-urlencode 'q=category=="restaurant"')" "restaurante-modelo-mare"
expect "consulta por refBeach" "$(q --data-urlencode type=PointOfInterest --data-urlencode 'q=refBeach=="urn:ngsi-ld:Beach:praia-modelo-do-farol"')" "coleta-modelo-farol-01"
expect "consulta geográfica (2 km do restaurante)" "$(q --data-urlencode type=Event --data-urlencode 'georel=near;maxDistance==2000' --data-urlencode geometry=Point --data-urlencode 'coordinates=[-35.2062,-5.8688]')" "show-bar-modelo-20261220"
expect "consulta de eventos por janela de datas" "$(q --data-urlencode type=Event --data-urlencode 'q=startDate[@value]>="2026-12-20T00:00:00Z";startDate[@value]<"2026-12-31T00:00:00Z"')" "restricao-banho-praia-modelo-20261224 show-bar-modelo-20261220"

ids=$(python3 -I -c "import json, sys; print(json.dumps([e['id'] for e in json.load(open(sys.argv[1]))]))" "$WORK/batch.json")
expect "remoção em lote" "$(orion -X POST http://localhost:1026/ngsi-ld/v1/entityOperations/delete -H 'Content-Type: application/json' -d "$ids" -o /dev/null -w '%{http_code}')" "204"

echo
if [ "$FAILS" -eq 0 ]; then echo "RESULTADO: TUDO OK"; else echo "RESULTADO: $FAILS falha(s)"; fi
[ "$FAILS" -eq 0 ]
