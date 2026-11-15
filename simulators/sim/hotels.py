import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from . import geo
from .client import ApiClient
from .config import Config
from .names import slug

log = logging.getLogger("sim.hotels")

PREFIX = "sim-"
CURRENCY = "BRL"
HIGH_SEASON = {12, 1, 2, 7}

CATEGORIES = {
    "hotel": ("Hotel", (3, 5)),
    "inn": ("Pousada", (2, 3)),
    "resort": ("Resort", (4, 5)),
    "hostel": ("Hostel", (1, 2)),
    "apartHotel": ("Flat", (3, 4)),
}
CATEGORY_WEIGHTS = {"hotel": 4, "inn": 3, "resort": 2, "hostel": 2, "apartHotel": 1}

STEMS = (
    "Vento Leste", "Brisa do Mar", "Duna Dourada", "Coral Azul", "Maré Mansa", "Sol Poente",
    "Areia Clara", "Jangada Nova", "Coqueiral", "Lua Cheia", "Mar Aberto", "Recanto Potiguar",
    "Pedra Lisa", "Onda Verde", "Cajueiro", "Farol Antigo", "Céu Aberto", "Porto Sereno",
    "Cais do Poente", "Sereia Morena",
)

ROOM_TYPES = {
    "hostel": (
        ("dorm", "Dormitório compartilhado", 1, 0, (8, 14), "1 cama em beliche", 1.0),
        ("priv", "Quarto privativo", 2, 0, (4, 8), "1 cama de casal", 2.6),
    ),
    "inn": (
        ("std", "Standard", 2, 1, (6, 10), "1 cama de casal", 1.0),
        ("sup", "Superior", 2, 2, (3, 6), "1 cama de casal e 1 sofá-cama", 1.3),
        ("fam", "Família", 3, 2, (2, 3), "1 cama de casal e 2 camas de solteiro", 1.7),
    ),
    "hotel": (
        ("std", "Standard", 2, 1, (15, 30), "1 cama de casal", 1.0),
        ("lux", "Luxo", 2, 2, (8, 15), "1 cama king", 1.4),
        ("fam", "Família", 3, 2, (4, 8), "1 cama de casal e 2 camas de solteiro", 1.8),
        ("ste", "Suíte", 2, 1, (2, 4), "1 cama king e sala de estar", 2.5),
    ),
    "resort": (
        ("std", "Standard", 2, 2, (20, 40), "1 cama king", 1.0),
        ("fam", "Família", 4, 2, (8, 15), "2 camas de casal", 1.6),
        ("ste", "Suíte vista mar", 2, 2, (3, 6), "1 cama king e varanda", 2.2),
        ("bang", "Bangalô", 2, 2, (2, 4), "1 cama king e piscina privativa", 3.0),
    ),
    "apartHotel": (
        ("studio", "Estúdio", 2, 1, (8, 14), "1 cama de casal", 1.0),
        ("apt1", "Apartamento 1 quarto", 2, 2, (6, 10), "1 cama de casal e 1 sofá-cama", 1.4),
        ("apt2", "Apartamento 2 quartos", 4, 2, (3, 6), "2 camas de casal", 2.0),
    ),
}

DESCRIPTIONS = {
    "hotel": "Hotel com recepção 24 horas e café da manhã regional.",
    "inn": "Pousada familiar com ambiente tranquilo.",
    "resort": "Resort com lazer completo para adultos e crianças.",
    "hostel": "Hostel com cozinha compartilhada e área de convivência.",
    "apartHotel": "Flat com cozinha equipada para estadias longas.",
}


@dataclass
class RoomPlan:
    body: dict
    factor: float


@dataclass
class HotelPlan:
    body: dict
    base_price: float
    rooms: list[RoomPlan] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.body["id"]


def base_price(category: str, stars: int) -> float:
    return {
        "hostel": 70 + 20 * (stars - 1),
        "inn": 180 + 40 * (stars - 2),
        "hotel": 260 + 130 * (stars - 3),
        "resort": 650 + 250 * (stars - 4),
        "apartHotel": 240 + 60 * (stars - 3),
    }[category]


def hotel_name(seed: str, index: int) -> str:
    stems = list(STEMS)
    random.Random(f"{seed}:hotel-names").shuffle(stems)
    stem = stems[index % len(stems)]
    return stem if index < len(stems) else f"{stem} {index // len(stems) + 1}"


def generate_hotel(seed: str, index: int) -> HotelPlan:
    rng = random.Random(f"{seed}:hotel:{index}")
    zone = geo.ZONES[index % len(geo.ZONES)]
    category = rng.choices(list(CATEGORY_WEIGHTS), weights=list(CATEGORY_WEIGHTS.values()))[0]
    prefix, (low, high) = CATEGORIES[category]
    stars = rng.randint(low, high)
    name = f"{prefix} {hotel_name(seed, index)}"
    hotel_id = PREFIX + slug(name)
    domain = f"{slug(name)}.example"

    amenities = ["wifi"]
    if category != "hostel" or rng.random() < 0.5:
        amenities.append("airConditioning")
    if category == "resort" or (category in ("hotel", "apartHotel") and stars >= 4) or rng.random() < 0.2:
        amenities.append("pool")
    if rng.random() < 0.6:
        amenities.append("parking")
    if category in ("inn", "hotel", "resort"):
        amenities.append("breakfast")
    if zone.coastal:
        amenities.append("beachfront")
    if rng.random() < 0.5:
        amenities.append("accessible")

    body = {
        "id": hotel_id,
        "name": name,
        "location": geo.point(rng, zone),
        "address": geo.address(rng, zone),
        "category": category,
        "starRating": stars,
        "checkInTime": rng.choice(("13:00", "14:00", "15:00")),
        "checkOutTime": rng.choice(("11:00", "12:00")),
        "amenities": amenities,
        "contactPoint": {"email": f"reservas@{domain}", "url": f"https://{domain}"},
        "description": DESCRIPTIONS[category],
    }
    plan = HotelPlan(body, base_price(category, stars))

    options = ROOM_TYPES[category]
    count = rng.randint(2, min(4, len(options)))
    chosen = [options[0], *sorted(rng.sample(options[1:], count - 1), key=options.index)]
    for room_id, room_name, adults, children, (umin, umax), beds, factor in chosen:
        plan.rooms.append(RoomPlan({
            "id": room_id,
            "name": room_name,
            "maxAdults": adults,
            "maxChildren": children,
            "totalUnits": rng.randint(umin, umax),
            "bedConfiguration": beds,
        }, factor))
    return plan


def generate(cfg: Config) -> list[HotelPlan]:
    return [generate_hotel(cfg.seed, i) for i in range(cfg.hotels)]


def is_high_season(day: date) -> bool:
    return day.month in HIGH_SEASON


def is_weekend(day: date) -> bool:
    return day.weekday() in (4, 5)


def minimum_stay(day: date) -> int | None:
    if (day.month, day.day) >= (12, 27) or (day.month, day.day) == (1, 1):
        return 3
    if is_high_season(day) and is_weekend(day):
        return 2
    return None


def night_price(hotel: HotelPlan, room: RoomPlan, day: date) -> float:
    price = hotel.base_price * room.factor
    if is_high_season(day):
        price *= 1.4
    if is_weekend(day):
        price *= 1.15
    return float(max(5, round(price / 5) * 5))


def occupancy(rng: random.Random, day: date, today: date) -> float:
    rate = 0.65 if is_high_season(day) else 0.35
    lead = (day - today).days
    if lead < 14:
        rate += 0.25 * (14 - max(lead, 0)) / 14
    if is_weekend(day):
        rate += 0.10
    rate += rng.uniform(-0.10, 0.10)
    return min(1.0, max(0.0, rate))


def generate_night(seed: str, hotel: HotelPlan, room: RoomPlan, day: date, today: date) -> dict:
    rng = random.Random(f"{seed}:night:{hotel.id}:{room.body['id']}:{day.isoformat()}")
    total = room.body["totalUnits"]
    night = {
        "roomType": room.body["id"],
        "stayDate": day.isoformat(),
        "availableUnits": total - round(total * occupancy(rng, day, today)),
        "pricePerNight": {"value": night_price(hotel, room, day), "currency": CURRENCY},
    }
    stay = minimum_stay(day)
    if stay:
        night["minimumStay"] = stay
    return night


def days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def hotel_path(hotel_id: str) -> str:
    return f"/v1/hotels/{hotel_id}"


def night_path(hotel_id: str, room_id: str, day: str) -> str:
    return f"{hotel_path(hotel_id)}/availability/{room_id}/{day}"


async def upsert_hotel(client: ApiClient, hotel: HotelPlan) -> bool:
    return await client.upsert("/v1/hotels", hotel_path(hotel.id), hotel.body)


async def upsert_room(client: ApiClient, hotel: HotelPlan, room: RoomPlan) -> bool:
    path = f"{hotel_path(hotel.id)}/room-types"
    return await client.upsert(path, f"{path}/{room.body['id']}", room.body)


async def upsert_night(client: ApiClient, hotel_id: str, night: dict) -> bool:
    return await client.upsert(f"{hotel_path(hotel_id)}/availability", night_path(hotel_id, night["roomType"], night["stayDate"]),
                               night, frozen=("roomType", "stayDate"))


async def seed(client: ApiClient, cfg: Config) -> None:
    hotels = generate(cfg)
    await asyncio.gather(*(upsert_hotel(client, h) for h in hotels))
    await asyncio.gather(*(upsert_room(client, h, r) for h in hotels for r in h.rooms))
    nights = [(h.id, generate_night(cfg.seed, h, r, d, cfg.start_date)) for h in hotels for r in h.rooms for d in days(cfg.start_date, cfg.nights)]
    await asyncio.gather(*(upsert_night(client, hotel_id, n) for hotel_id, n in nights))
    log.info("hotéis: %d, tipos de quarto: %d, noites: %d", len(hotels), sum(len(h.rooms) for h in hotels), len(nights))


class Runner:
    name = "hotels"
    changes_per_tick = 10

    def __init__(self, client: ApiClient, cfg: Config, rng: random.Random | None = None):
        self.client = client
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.hotels = {h.id: h for h in generate(cfg)}
        self.totals: dict[tuple[str, str], int] = {}
        self.available: dict[tuple[str, str, str], int] = {}
        self.horizon_start: date | None = None

    async def load(self) -> None:
        today = datetime.now(UTC).date()
        for hotel in self.hotels.values():
            for room in await self.client.get(f"{hotel_path(hotel.id)}/room-types", limit=1000):
                self.totals[(hotel.id, room["id"])] = room["totalUnits"]
            nights = await self.client.get(f"{hotel_path(hotel.id)}/availability", limit=1000,
                                           **{"from": today.isoformat(), "to": (today + timedelta(days=self.cfg.nights)).isoformat()})
            for n in nights:
                self.available[(hotel.id, n["roomType"], n["stayDate"])] = n["availableUnits"]
        log.info("run hotéis: %d tipos de quarto, %d noites carregadas", len(self.totals), len(self.available))

    async def fill_horizon(self, today: date) -> None:
        self.horizon_start = today
        for key in [k for k in self.available if k[2] < today.isoformat()]:
            del self.available[key]
        created = 0
        for hotel in self.hotels.values():
            for room in hotel.rooms:
                if (hotel.id, room.body["id"]) not in self.totals:
                    continue
                for day in days(today, self.cfg.nights):
                    key = (hotel.id, room.body["id"], day.isoformat())
                    if key in self.available:
                        continue
                    night = generate_night(self.cfg.seed, hotel, room, day, today)
                    if await upsert_night(self.client, hotel.id, night):
                        self.available[key] = night["availableUnits"]
                        created += 1
        if created:
            log.info("run hotéis: %d noites criadas no horizonte", created)

    async def tick(self) -> None:
        today = datetime.now(UTC).date()
        if self.horizon_start != today:
            await self.fill_horizon(today)
        if not self.available:
            return
        keys = list(self.available)
        weights = [1 / (1 + (date.fromisoformat(k[2]) - today).days / 7) for k in keys]
        for key in set(self.rng.choices(keys, weights=weights, k=self.changes_per_tick)):
            hotel_id, room_id, day = key
            current, total = self.available[key], self.totals[(hotel_id, room_id)]
            delta = -self.rng.randint(1, 2) if self.rng.random() < 0.7 else self.rng.randint(1, 2)
            new = min(total, max(0, current + delta))
            if new != current and await self.client.patch(night_path(hotel_id, room_id, day), {"availableUnits": new}):
                self.available[key] = new


def fits(room: dict, adults: int, children: int, rooms: int) -> bool:
    return adults <= room["maxAdults"] * rooms and adults + children <= (room["maxAdults"] + room["maxChildren"]) * rooms


def scenario_start(cfg: Config, offset: int, nights: int) -> date | None:
    for shift in range(offset, cfg.nights - nights + 1):
        start = cfg.start_date + timedelta(days=shift)
        if all((minimum_stay(d) or 1) <= nights for d in days(start, nights)):
            return start
    return None


SCENARIOS = (
    ("casal, 3 noites", 2, 0, 1, 7, 3),
    ("família 2+2, 5 noites", 2, 2, 1, 14, 5),
    ("4 adultos em 2 quartos, 2 noites", 4, 0, 2, 3, 2),
)


async def check(client: ApiClient, cfg: Config) -> bool:
    ok = True

    def report(passed: bool, message: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'OK    ' if passed else 'FALHA '} {message}")

    hotels = generate(cfg)
    found = await asyncio.gather(*(client.request("GET", hotel_path(h.id)) for h in hotels))
    listed = {h.id for h, r in zip(hotels, found) if r.status_code == 200}
    missing = [h.id for h in hotels if h.id not in listed]
    report(not missing, f"hotéis consultáveis: {len(hotels) - len(missing)}/{len(hotels)}" + (f", faltam {missing}" if missing else ""))

    end = cfg.start_date + timedelta(days=cfg.nights)
    rooms: dict[tuple[str, str], dict] = {}
    for hotel in hotels:
        if hotel.id not in listed:
            continue
        found = {r["id"]: r for r in await client.get(f"{hotel_path(hotel.id)}/room-types", limit=1000)}
        rooms.update({(hotel.id, k): v for k, v in found.items()})
        expected = {r.body["id"] for r in hotel.rooms}
        report(expected <= set(found), f"{hotel.id}: tipos de quarto {sorted(found)}")
        nights = await client.get(f"{hotel_path(hotel.id)}/availability", limit=1000,
                                  **{"from": cfg.start_date.isoformat(), "to": end.isoformat()})
        want = len(expected) * cfg.nights
        report(len(nights) >= want, f"{hotel.id}: noites {len(nights)}/{want}")

    for label, adults, children, n_rooms, offset, n_nights in SCENARIOS:
        start = scenario_start(cfg, offset, n_nights)
        if start is None:
            print(f"IGNORADO {label}: fora do horizonte de {cfg.nights} noites")
            continue
        params = {"checkIn": start.isoformat(), "checkOut": (start + timedelta(days=n_nights)).isoformat(),
                  "adults": adults, "children": children, "rooms": n_rooms}
        offers = [o for o in await client.get("/v1/availability", **params) if (o["hotel"], o["roomType"]) in rooms]
        problems = []
        for o in offers:
            room = rooms[(o["hotel"], o["roomType"])]
            prices = [p["value"] for p in o["pricePerNight"]]
            if not fits(room, adults, children, n_rooms):
                problems.append(f"{o['hotel']}/{o['roomType']}: capacidade")
            if o["availableUnits"] < n_rooms or len(prices) != n_nights:
                problems.append(f"{o['hotel']}/{o['roomType']}: noites ou unidades")
            if abs(o["totalPrice"]["value"] - round(sum(prices) * n_rooms, 2)) > 0.01:
                problems.append(f"{o['hotel']}/{o['roomType']}: total")
        report(bool(offers) and not problems,
               f"busca {label} ({params['checkIn']} a {params['checkOut']}): {len(offers)} ofertas" + (f", {problems}" if problems else ""))
    return ok
