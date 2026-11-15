import asyncio
import logging
import random
from collections import Counter
from dataclasses import dataclass, field

from . import geo
from .client import ApiClient
from .config import Config
from .names import slug

log = logging.getLogger("sim.beaches")

PREFIX = "sim-"
POINT_RADIUS = 300
COASTAL = tuple(z for z in geo.ZONES if z.coastal)
STATION_ORDER = ("orla-sul", "orla-norte", "orla-central")

BEACH_STEMS = (
    "Praia do Coqueiral", "Praia dos Arrecifes", "Praia das Jangadas", "Praia da Pedra Lisa", "Praia do Farol Velho",
    "Praia da Barra Nova", "Praia das Marisqueiras", "Praia do Vento Leste", "Praia da Duna Branca",
)

PROFILES = {
    "orla-sul": {
        "beachType": (["whiteSand", "urban"], ["strongWaves"]),
        "facilities": (["promenade", "lifeGuard", "litterBins"], ["showers", "toilets", "sunshadeRental", "surfPracticeArea"]),
        "accessType": (["onFoot", "publicTransport"], ["privateVehicle"]),
        "occupationRate": ("high", "medium"),
    },
    "orla-central": {
        "beachType": (["urban"], ["calmWaters", "whiteSand"]),
        "facilities": (["promenade", "lifeGuard", "litterBins"], ["touristOffice", "accessforDisabled", "toilets"]),
        "accessType": (["onFoot", "publicTransport"], ["privateVehicle"]),
        "occupationRate": ("medium", "high"),
    },
    "orla-norte": {
        "beachType": (["whiteSand"], ["windy", "isolated", "calmWaters"]),
        "facilities": (["litterBins"], ["sunLoungerRental", "waterCraftRental", "lifeGuard"]),
        "accessType": (["privateVehicle"], ["boat", "onFoot"]),
        "occupationRate": ("low", "medium"),
    },
}


@dataclass
class Beach:
    body: dict
    points: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.body["id"]


@dataclass
class Plan:
    stations: list[dict]
    beaches: list[Beach]


def nth(names: tuple[str, ...], index: int) -> str:
    name = names[index % len(names)]
    return name if index < len(names) else f"{name} {index // len(names) + 1}"


def generate_station(seed: str, index: int) -> dict:
    rng = random.Random(f"{seed}:station:{index}")
    zone = next(z for z in geo.ZONES if z.key == STATION_ORDER[index % len(STATION_ORDER)])
    suffix = "" if index < len(STATION_ORDER) else f" {index // len(STATION_ORDER) + 1}"
    name = f"Estação Meteorológica {zone.name}{suffix}"
    return {
        "id": f"{PREFIX}estacao-{zone.key}" + (f"-{index // len(STATION_ORDER) + 1}" if suffix else ""),
        "name": name,
        "location": geo.point(rng, zone),
        "address": geo.address(rng, zone),
        "description": "Estação meteorológica automática com pluviômetro.",
    }


def pick(rng: random.Random, required: list[str], optional: list[str]) -> list[str]:
    return required + [x for x in optional if rng.random() < 0.6]


def nearest(location: list[float], stations: list[dict]) -> dict:
    return min(stations, key=lambda s: geo.distance_m(location, s["location"]))


def generate_beach(seed: str, index: int, stations: list[dict], points: int) -> Beach:
    rng = random.Random(f"{seed}:beach:{index}")
    zone = COASTAL[index % len(COASTAL)]
    profile = PROFILES[zone.key]
    name = nth(BEACH_STEMS, index)
    location = geo.point(rng, zone)
    body = {
        "id": PREFIX + slug(name),
        "name": name,
        "location": location,
        "address": geo.address(rng, zone),
        "beachType": pick(rng, *profile["beachType"]),
        "facilities": pick(rng, *profile["facilities"]),
        "accessType": pick(rng, *profile["accessType"]),
        "length": float(rng.randrange(800, 3501, 50)),
        "width": float(rng.randrange(20, 81, 5)),
        "occupationRate": rng.choice(profile["occupationRate"]),
        "refWeatherStation": nearest(location, stations)["id"],
        "description": f"Praia na {zone.name}.",
    }
    beach = Beach(body)
    for n in range(1, points + 1):
        beach.points.append({
            "id": f"{PREFIX}coleta-{slug(name)}-{n:02d}",
            "name": f"Ponto de coleta {n:02d}, {name}",
            "location": geo.around(rng, location, POINT_RADIUS),
            "refBeach": beach.id,
        })
    return beach


def generate(cfg: Config) -> Plan:
    stations = [generate_station(cfg.seed, i) for i in range(cfg.stations)]
    return Plan(stations, [generate_beach(cfg.seed, i, stations, cfg.points_per_beach) for i in range(cfg.beaches)])


async def seed(client: ApiClient, cfg: Config) -> None:
    plan = generate(cfg)
    await asyncio.gather(*(client.upsert("/v1/weather-stations", f"/v1/weather-stations/{s['id']}", s) for s in plan.stations))
    await asyncio.gather(*(client.upsert("/v1/beaches", f"/v1/beaches/{b.id}", b.body) for b in plan.beaches))
    points = [p for b in plan.beaches for p in b.points]
    await asyncio.gather(*(client.upsert("/v1/sampling-points", f"/v1/sampling-points/{p['id']}", p) for p in points))
    log.info("estações: %d, praias: %d, pontos de coleta: %d", len(plan.stations), len(plan.beaches), len(points))


async def check(client: ApiClient, cfg: Config) -> bool:
    ok = True

    def report(passed: bool, message: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'OK    ' if passed else 'FALHA '} {message}")

    async def fetch(route: str, items: list[dict]) -> dict[str, dict]:
        responses = await asyncio.gather(*(client.request("GET", f"{route}/{i['id']}") for i in items))
        return {i["id"]: r.json() for i, r in zip(items, responses) if r.status_code == 200}

    plan = generate(cfg)
    points = [p for b in plan.beaches for p in b.points]
    found_stations = await fetch("/v1/weather-stations", plan.stations)
    found_beaches = await fetch("/v1/beaches", [b.body for b in plan.beaches])
    found_points = await fetch("/v1/sampling-points", points)
    for label, want, got in (("estações", plan.stations, found_stations), ("praias", [b.body for b in plan.beaches], found_beaches),
                             ("pontos de coleta", points, found_points)):
        missing = [i["id"] for i in want if i["id"] not in got]
        report(not missing, f"{label} consultáveis: {len(want) - len(missing)}/{len(want)}" + (f", faltam {missing}" if missing else ""))

    wrong = [b.id for b in plan.beaches
             if found_beaches.get(b.id, {}).get("refWeatherStation") != nearest(b.body["location"], plan.stations)["id"]
             or found_beaches[b.id]["refWeatherStation"] not in found_stations]
    report(not wrong, f"praias ligadas à estação mais próxima: {len(plan.beaches) - len(wrong)}/{len(plan.beaches)}"
           + (f", erradas: {wrong}" if wrong else ""))

    listed = await client.get("/v1/beaches", limit=1000)
    linked = Counter(b.get("refWeatherStation") for b in listed if b["id"].startswith(PREFIX))
    alone = [s["id"] for s in plan.stations if not linked[s["id"]]]
    summary = ", ".join(f"{s['id']} ({linked[s['id']]})" for s in plan.stations)
    report(not alone, f"estações com praias: {summary}")

    mismatched = []
    for b in plan.beaches:
        listed_points = await client.get("/v1/sampling-points", beach=b.id, limit=1000)
        ids = {p["id"] for p in listed_points if p["id"].startswith(PREFIX)}
        back = all(found_points.get(p["id"], {}).get("refBeach") == b.id for p in b.points)
        if ids != {p["id"] for p in b.points} or not back:
            mismatched.append(b.id)
    report(not mismatched, f"pontos por praia, nos dois sentidos: {len(plan.beaches) - len(mismatched)}/{len(plan.beaches)}"
           + (f", divergentes: {mismatched}" if mismatched else ""))
    return ok
