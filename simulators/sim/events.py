import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from . import geo, venues
from .client import ApiClient
from .config import Config
from .names import slug

log = logging.getLogger("sim.events")

PREFIX = "sim-"
BORDER = 50
SHARES = (("show", 0.45), ("workshop", 0.25), ("festival", 0.15))

GENRES = ("Forró pé de serra", "Samba de roda", "MPB acústica", "Choro", "Rock potiguar", "Coco de roda", "Jazz na varanda")
WORKSHOPS = (
    ("Oficina de tapioca", ["gastronomy"], None),
    ("Oficina de renda de bilro", ["history"], None),
    ("Aula aberta de ioga", ["wellness"], None),
    ("Oficina de surfe para iniciantes", ["outdoorActivities"], "coastal"),
    ("Oficina de horta urbana", ["parksAndGardens"], None),
)
FESTIVALS = (
    ("Festival Gastronômico da Orla", ["gastronomy", "spectacle"]),
    ("Festival de Música Potiguar", ["spectacle"]),
    ("Festival do Caju", ["gastronomy"]),
    ("Festival de Coco e Ciranda", ["spectacle"]),
    ("Festival das Jangadas", ["spectacle", "outdoorActivities"]),
    ("Festival de Frutos do Mar", ["gastronomy"]),
)
CONFERENCES = (
    "Congresso Nordestino de Turismo", "Simpósio de Oceanografia Costeira", "Congresso de Tecnologia Urbana",
    "Encontro de Gestão Hoteleira", "Congresso de Saúde Pública", "Fórum de Energias Renováveis",
)


@dataclass
class Event:
    body: dict
    kind: str

    @property
    def id(self) -> str:
        return self.body["id"]

    @property
    def start(self) -> str:
        return self.body["startDate"]

    @property
    def end(self) -> str:
        return self.body["endDate"]


def utc_text(day: date, at: time) -> str:
    return datetime.combine(day, at, venues.LOCAL).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick_day(rng: random.Random, cfg: Config, weekdays: tuple[int, ...], length: int = 1) -> date:
    options = [cfg.start_date + timedelta(days=i) for i in range(cfg.event_days - length + 1)]
    return rng.choice([d for d in options if d.weekday() in weekdays])


def prices(rng: random.Random, low: int, high: int) -> dict:
    start = rng.randrange(low, high + 1, 5)
    return {"isAccessibleForFree": False, "eventPriceFrom": {"value": float(start), "currency": "BRL"},
            "eventPriceTo": {"value": float(start + rng.randrange(0, high - low + 1, 5)), "currency": "BRL"}}


def nth(names: tuple, index: int):
    item = names[index % len(names)]
    return item, (f" {index // len(names) + 1}" if index >= len(names) else "")


def place_of(venue: venues.Venue) -> dict:
    return {"location": venue.body["location"], "address": venue.body["address"], "venueName": venue.body["name"],
            "refPointOfInterest": {venue.kind: venue.id}}


def free_place(rng: random.Random, zone: geo.Zone, venue_name: str) -> dict:
    return {"location": geo.point(rng, zone), "address": geo.address(rng, zone), "venueName": venue_name}


def show(cfg: Config, index: int, bars: list[venues.Venue]) -> dict:
    rng = random.Random(f"{cfg.seed}:show:{index}")
    bar = bars[index % len(bars)]
    day = pick_day(rng, cfg, (3, 4, 5, 6))
    opens = rng.choice((time(20), time(21)))
    body = {
        "name": f"{rng.choice(GENRES)} no {bar.body['name']}",
        "startDate": utc_text(day, opens),
        "endDate": utc_text(day, time(23, 30)),
        "category": ["spectacle"], "eventScale": "small", "audience": ["adult"],
        "maximumAttendeeCapacity": bar.body["capacity"], **place_of(bar),
        "description": "Apresentação de música ao vivo.",
    }
    body |= prices(rng, 10, 40) if rng.random() < 0.7 else {"isAccessibleForFree": True}
    return body


def workshop(cfg: Config, index: int, restaurants: list[venues.Venue]) -> dict:
    rng = random.Random(f"{cfg.seed}:workshop:{index}")
    (name, category, where), suffix = nth(WORKSHOPS, index)
    day = pick_day(rng, cfg, (5,))
    opens = rng.choice((time(9), time(14)))
    if category == ["gastronomy"] and restaurants:
        regional = [r for r in restaurants if "regional" in r.body["cuisine"]] or restaurants
        place = place_of(rng.choice(regional))
    else:
        zones = [z for z in geo.ZONES if z.coastal] if where == "coastal" else list(geo.ZONES)
        zone = rng.choice(zones)
        place = free_place(rng, zone, f"Centro Comunitário {zone.name}")
    return {
        "name": name + suffix,
        "startDate": utc_text(day, opens), "endDate": utc_text(day, time(opens.hour + 3)),
        "category": category, "eventScale": "small", "audience": [rng.choice(("allPublic", "family"))],
        "maximumAttendeeCapacity": rng.randrange(15, 41, 5), "isAccessibleForFree": True, **place,
        "description": "Oficina comunitária com inscrição gratuita.",
    }


def festival(cfg: Config, index: int) -> dict:
    rng = random.Random(f"{cfg.seed}:festival:{index}")
    (name, category), suffix = nth(FESTIVALS, index)
    length = rng.choice((2, 3))
    day = pick_day(rng, cfg, (4,), length)
    zone = rng.choice([z for z in geo.ZONES if z.coastal])
    capacity = rng.randrange(2000, 15001, 500)
    body = {
        "name": name + suffix,
        "startDate": utc_text(day, time(16)), "endDate": utc_text(day + timedelta(days=length - 1), time(23, 59)),
        "category": category, "eventScale": "large" if capacity > 5000 else "medium", "audience": ["allPublic"],
        "maximumAttendeeCapacity": capacity, **free_place(rng, zone, f"Calçadão da {zone.name}"),
        "wheelChairAccessible": True, "description": "Festival ao ar livre na orla.",
    }
    body |= prices(rng, 20, 80) if rng.random() < 0.5 else {"isAccessibleForFree": True}
    return body


def convention_center(seed: str) -> dict:
    zone = next(z for z in geo.ZONES if z.key == "orla-central")
    return free_place(random.Random(f"{seed}:convention-center"), zone, "Centro de Convenções Orla Central")


def conference(cfg: Config, index: int) -> dict:
    rng = random.Random(f"{cfg.seed}:conference:{index}")
    name, suffix = nth(CONFERENCES, index)
    length = rng.choice((2, 3))
    day = pick_day(rng, cfg, (0, 1, 2) if length == 3 else (0, 1, 2, 3), length)
    capacity = rng.randrange(300, 3001, 100)
    return {
        "name": name + suffix,
        "startDate": utc_text(day, time(8)), "endDate": utc_text(day + timedelta(days=length - 1), time(18)),
        "category": ["conference"], "eventScale": "large" if capacity >= 1500 else "medium", "audience": ["adult"],
        "maximumAttendeeCapacity": capacity, **convention_center(cfg.seed), **prices(rng, 150, 900),
        "wheelChairAccessible": True, "description": "Congresso com palestras e sessões técnicas.",
    }


def counts(total: int) -> dict[str, int]:
    out = {kind: round(total * share) for kind, share in SHARES}
    out["conference"] = max(0, total - sum(out.values()))
    return out


def generate(cfg: Config) -> list[Event]:
    places = venues.generate(cfg)
    bars = [v for v in places if v.kind == "bar"]
    restaurants = [v for v in places if v.kind == "restaurant"]
    amount = counts(cfg.events)
    if not bars:
        amount["conference"] += amount.pop("show")
    builders = {
        "show": lambda i: show(cfg, i, bars),
        "workshop": lambda i: workshop(cfg, i, restaurants),
        "festival": lambda i: festival(cfg, i),
        "conference": lambda i: conference(cfg, i),
    }
    events, used = [], set()
    for kind, total in amount.items():
        for i in range(total):
            body = builders[kind](i)
            base = f"{PREFIX}{slug(body['name'])}-{body['startDate'][:10].replace('-', '')}"
            event_id, n = base, 2
            while event_id in used:
                event_id, n = f"{base}-{n}", n + 1
            used.add(event_id)
            events.append(Event({"id": event_id, **body, "eventStatus": ["scheduled"]}, kind))
    rng = random.Random(f"{cfg.seed}:status")
    for event, status in zip(rng.sample(events, min(3, len(events))), ("cancelled", "cancelled", "postponed")):
        event.body["eventStatus"] = [status]
    return events


async def seed(client: ApiClient, cfg: Config) -> None:
    events = generate(cfg)
    await asyncio.gather(*(client.upsert("/v1/events", f"/v1/events/{e.id}", e.body) for e in events))
    totals = {k: sum(e.kind == k for e in events) for k in ("show", "workshop", "festival", "conference")}
    log.info("eventos: %d (%s)", len(events), ", ".join(f"{k} {v}" for k, v in totals.items()))


def windows(cfg: Config) -> list[tuple[str, date, date]]:
    start = cfg.start_date
    friday = next(start + timedelta(days=i) for i in range(7, 14) if (start + timedelta(days=i)).weekday() == 4)
    found = [("próximos 7 dias", start, start + timedelta(days=7)), ("fim de semana", friday, friday + timedelta(days=3))]
    if cfg.event_days >= 45:
        found.append(("dias 30 a 45", start + timedelta(days=30), start + timedelta(days=45)))
    return found


def overlaps(event: Event, first: date, last: date) -> bool:
    return event.start < f"{last.isoformat()}T00:00:00Z" and event.end > f"{first.isoformat()}T00:00:00Z"


def classify(events: list[Event], zone: geo.Zone) -> tuple[set[str], set[str]]:
    inside, border = set(), set()
    for e in events:
        distance = geo.distance_m(e.body["location"], zone.center)
        if abs(distance - zone.radius) < BORDER:
            border.add(e.id)
        elif distance < zone.radius:
            inside.add(e.id)
    return inside, border


async def check(client: ApiClient, cfg: Config) -> bool:
    ok = True

    def report(passed: bool, message: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'OK    ' if passed else 'FALHA '} {message}")

    events = generate(cfg)
    responses = await asyncio.gather(*(client.request("GET", f"/v1/events/{e.id}") for e in events))
    missing = [e.id for e, r in zip(events, responses) if r.status_code != 200]
    report(not missing, f"eventos consultáveis: {len(events) - len(missing)}/{len(events)}" + (f", faltam {missing}" if missing else ""))

    async def agenda(**params) -> list[dict]:
        return [e for e in await client.get("/v1/events", limit=1000, **params) if e["id"].startswith(PREFIX)]

    def compare(label: str, got: list[dict], want: set[str], ignore: set[str] = frozenset(), ordered: bool = False) -> None:
        ids = {e["id"] for e in got} - set(ignore)
        starts = [e["startDate"] for e in got]
        extra, lacking = sorted(ids - want), sorted(want - ids)
        unordered = ordered and starts != sorted(starts)
        detail = (f", sobrando {extra}" if extra else "") + (f", faltando {lacking}" if lacking else "") + (", fora de ordem" if unordered else "")
        report(not extra and not lacking and not unordered, f"{label}: {len(want)} eventos{detail}")

    for label, first, last in windows(cfg):
        want = {e.id for e in events if overlaps(e, first, last)}
        compare(f"janela {label} ({first} a {last}), em ordem de início",
                await agenda(**{"from": first.isoformat(), "to": last.isoformat()}), want, ordered=True)

    for zone in geo.ZONES:
        inside, border = classify(events, zone)
        near = f"{zone.center[0]},{zone.center[1]}"
        compare(f"área {zone.name} ({zone.radius} m)", await agenda(near=near, maxDistance=zone.radius), inside, border)

    label, first, last = windows(cfg)[-1]
    zone = next(z for z in geo.ZONES if z.key == "orla-central")
    inside, border = classify(events, zone)
    want = {e.id for e in events if e.id in inside and overlaps(e, first, last)}
    got = await agenda(**{"from": first.isoformat(), "to": last.isoformat()}, near=f"{zone.center[0]},{zone.center[1]}", maxDistance=zone.radius)
    compare(f"janela {label} e área {zone.name}", got, want, border)
    return ok
