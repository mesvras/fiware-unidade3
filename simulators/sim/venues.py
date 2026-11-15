import asyncio
import logging
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from . import geo, hotels
from .client import ApiClient
from .config import Config
from .names import slug

log = logging.getLogger("sim.venues")

PREFIX = "sim-"
LOCAL = timezone(timedelta(hours=-3))
LIMITED_RATIO = 0.7
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

CUISINES = {
    "regional": (("Restaurante", "Casa"), (2, 2)),
    "frutos do mar": (("Peixaria", "Restaurante"), (2, 3)),
    "japonesa": (("Sushi", "Temakeria"), (2, 4)),
    "italiana": (("Cantina", "Trattoria"), (2, 3)),
    "churrasco": (("Churrascaria",), (3, 3)),
    "vegetariana": (("Bistrô", "Restaurante"), (1, 2)),
    "pizza": (("Pizzaria",), (1, 2)),
}
BAR_CUISINE = "petiscos"

RESTAURANT_STEMS = (
    "Maresia", "Canto da Praia", "Sabor Potiguar", "Rede Branca", "Cajá", "Mangaba", "Tapioca de Ouro", "Varanda",
    "Brasa Viva", "Pé de Areia", "Vela Branca", "Sol Nascente", "Mesa Farta", "Caranguejo Azul", "Lagosta Dourada",
    "Terra e Mar", "Porto Velho", "Jardim Secreto", "Ponta do Sal", "Sertão", "Engenho", "Barlavento", "Sotavento",
    "Manguezal", "Cacimba", "Graviola", "Carnaúba", "Oiticica",
)
BAR_STEMS = (
    "Saideira", "Esquina", "Lua Nova", "Maré Cheia", "Ventania", "Biruta", "Arrecife", "Cais", "Batuque",
    "Forró da Lua", "Pôr do Sol", "Coqueiro Torto", "Garoa", "Canoa", "Bossa", "Xaréu",
)


@dataclass
class Venue:
    body: dict
    kind: str
    popularity: float

    @property
    def id(self) -> str:
        return self.body["id"]

    @property
    def path(self) -> str:
        return f"/v1/{self.kind}s/{self.id}"


def unique_name(seed: str, kind: str, stems: tuple[str, ...], index: int) -> str:
    shuffled = list(stems)
    random.Random(f"{seed}:{kind}-names").shuffle(shuffled)
    stem = shuffled[index % len(shuffled)]
    return stem if index < len(shuffled) else f"{stem} {index // len(shuffled) + 1}"


def restaurant_hours(rng: random.Random, cuisine: str) -> list[dict]:
    days = list(DAYS[1:] if rng.random() < 0.4 else DAYS)
    dinner = {"dayOfWeek": days, "opens": rng.choice(("18:00", "18:30")), "closes": rng.choice(("23:00", "23:30"))}
    if cuisine == "pizza":
        return [dinner]
    return [{"dayOfWeek": days, "opens": rng.choice(("11:00", "11:30")), "closes": "15:00"}, dinner]


def bar_hours(rng: random.Random) -> list[dict]:
    weekdays = ["Tuesday", "Wednesday"] if rng.random() < 0.5 else ["Monday", "Tuesday", "Wednesday"]
    return [
        {"dayOfWeek": weekdays, "opens": "17:00", "closes": "23:00"},
        {"dayOfWeek": ["Thursday", "Friday", "Saturday"], "opens": "17:00", "closes": "02:00"},
        {"dayOfWeek": ["Sunday"], "opens": "16:00", "closes": "23:00"},
    ]


def price_range(rng: random.Random, low: int, high: int, coastal: bool) -> str:
    level = rng.randint(low, high) + (1 if coastal and rng.random() < 0.3 else 0)
    return "$" * min(4, level)


def generate_restaurant(seed: str, index: int) -> Venue:
    rng = random.Random(f"{seed}:restaurant:{index}")
    zone = geo.ZONES[index % len(geo.ZONES)]
    weights = [4 if (c == "frutos do mar" and zone.coastal) else 2 if c == "regional" else 1 for c in CUISINES]
    cuisine = rng.choices(list(CUISINES), weights=weights)[0]
    prefixes, (low, high) = CUISINES[cuisine]
    name = f"{rng.choice(prefixes)} {unique_name(seed, 'restaurant', RESTAURANT_STEMS, index)}"
    body = {
        "id": PREFIX + slug(name),
        "name": name,
        "location": geo.point(rng, zone),
        "address": geo.address(rng, zone),
        "capacity": rng.randrange(40, 201, 10),
        "occupancy": 0,
        "cuisine": [cuisine],
        "priceRange": price_range(rng, low, high, zone.coastal),
        "openingHoursSpecification": restaurant_hours(rng, cuisine),
        "contactPoint": {"url": f"https://{slug(name)}.example"},
        "description": f"Restaurante de cozinha {cuisine}.",
    }
    return Venue(body, "restaurant", rng.uniform(0.6, 1.1))


def generate_bar(seed: str, index: int) -> Venue:
    rng = random.Random(f"{seed}:bar:{index}")
    zone = geo.ZONES[index % len(geo.ZONES)]
    prefix = rng.choice(("Bar", "Boteco", "Quiosque") if zone.coastal else ("Bar", "Boteco"))
    name = f"{prefix} {unique_name(seed, 'bar', BAR_STEMS, index)}"
    body = {
        "id": PREFIX + slug(name),
        "name": name,
        "location": geo.point(rng, zone),
        "address": geo.address(rng, zone),
        "capacity": rng.randrange(30, 121, 10),
        "occupancy": 0,
        "cuisine": [BAR_CUISINE],
        "priceRange": price_range(rng, 1, 2, zone.coastal),
        "openingHoursSpecification": bar_hours(rng),
        "contactPoint": {"url": f"https://{slug(name)}.example"},
        "description": "Bar com petiscos e música ao vivo em alguns dias.",
    }
    return Venue(body, "bar", rng.uniform(0.6, 1.1))


def generate(cfg: Config) -> list[Venue]:
    return [generate_restaurant(cfg.seed, i) for i in range(cfg.restaurants)] + [generate_bar(cfg.seed, i) for i in range(cfg.bars)]


def is_open(hours: list[dict], moment: datetime) -> bool:
    now = moment.strftime("%H:%M")
    today, yesterday = DAYS[moment.weekday()], DAYS[(moment.weekday() - 1) % 7]
    for spec in hours:
        opens, closes = spec["opens"], spec["closes"]
        if opens < closes:
            if today in spec["dayOfWeek"] and opens <= now < closes:
                return True
        elif (today in spec["dayOfWeek"] and now >= opens) or (yesterday in spec["dayOfWeek"] and now < closes):
            return True
    return False


def demand(kind: str, moment: datetime) -> float:
    hour = moment.hour + moment.minute / 60
    if kind == "restaurant":
        rate = 0.85 * math.exp(-((hour - 13) / 1.0) ** 2) + 0.9 * math.exp(-((hour - 20.5) / 1.3) ** 2) + 0.05
        weekend = moment.weekday() >= 5 or (moment.weekday() == 4 and hour >= 17)
        return min(1.0, rate * (1.15 if weekend else 1.0))
    late = hour + 24 if hour < 6 else hour
    night = moment - timedelta(hours=6)
    rate = 0.9 * math.exp(-((late - 22.5) / 2.0) ** 2) + 0.05
    return min(1.0, rate * (1.2 if night.weekday() in (3, 4, 5) else 0.75))


def target_occupancy(venue: Venue, moment: datetime) -> int:
    if not is_open(venue.body["openingHoursSpecification"], moment):
        return 0
    capacity = venue.body["capacity"]
    return min(capacity, round(capacity * demand(venue.kind, moment) * venue.popularity))


def next_occupancy(rng: random.Random, venue: Venue, current: int, moment: datetime) -> int:
    target = target_occupancy(venue, moment)
    step = round((target - current) * 0.5)
    noise = rng.randint(-2, 2) if target > 0 else 0
    return min(venue.body["capacity"], max(0, current + step + noise))


def occupancy_of(item: dict) -> int:
    occupancy = item["occupancy"]
    return occupancy["value"] if isinstance(occupancy, dict) else occupancy


def local_now() -> datetime:
    return datetime.now(UTC).astimezone(LOCAL)


async def upsert(client: ApiClient, venue: Venue, moment: datetime) -> bool:
    body = {**venue.body, "occupancy": target_occupancy(venue, moment)}
    return await client.upsert(f"/v1/{venue.kind}s", venue.path, body)


async def seed(client: ApiClient, cfg: Config) -> None:
    venues = generate(cfg)
    moment = local_now()
    await asyncio.gather(*(upsert(client, v, moment) for v in venues))
    log.info("restaurantes: %d, bares: %d", cfg.restaurants, cfg.bars)


class Runner:
    name = "restaurants"

    def __init__(self, client: ApiClient, cfg: Config, rng: random.Random | None = None):
        self.client = client
        self.rng = rng or random.Random()
        self.venues = generate(cfg)
        self.occupancy: dict[str, int] = {}

    async def load(self) -> None:
        for venue in self.venues:
            response = await self.client.request("GET", venue.path)
            if response.status_code == 200:
                self.occupancy[venue.id] = occupancy_of(response.json())
        log.info("run restaurantes e bares: %d carregados", len(self.occupancy))

    async def tick(self) -> None:
        moment = local_now()

        async def update(venue: Venue) -> None:
            current = self.occupancy[venue.id]
            new = next_occupancy(self.rng, venue, current, moment)
            if new != current and await self.client.patch(venue.path, {"occupancy": new}):
                self.occupancy[venue.id] = new

        await asyncio.gather(*(update(v) for v in self.venues if v.id in self.occupancy))


def expected_level(capacity: int, occupancy: int) -> str:
    if occupancy >= capacity:
        return "full"
    return "limited" if occupancy / capacity >= LIMITED_RATIO else "available"


async def check(client: ApiClient, cfg: Config) -> bool:
    ok = True

    def report(passed: bool, message: str) -> None:
        nonlocal ok
        ok &= passed
        print(f"{'OK    ' if passed else 'FALHA '} {message}")

    venues = generate(cfg)
    responses = await asyncio.gather(*(client.request("GET", v.path) for v in venues))
    found = {v.id: r.json() for v, r in zip(venues, responses) if r.status_code == 200}
    for kind, label in (("restaurant", "restaurantes"), ("bar", "bares")):
        group = [v for v in venues if v.kind == kind]
        missing = [v.id for v in group if v.id not in found]
        report(not missing, f"{label} consultáveis: {len(group) - len(missing)}/{len(group)}" + (f", faltam {missing}" if missing else ""))

    wrong = []
    for v in venues:
        item = found.get(v.id)
        if item is None:
            continue
        if kind_of(item) != v.kind:
            wrong.append(f"{v.id}: categoria")
        if item.get("availabilityLevel") != expected_level(item["capacity"], occupancy_of(item)):
            wrong.append(f"{v.id}: availabilityLevel")
    report(not wrong, "categoria e availabilityLevel coerentes" + (f": {wrong}" if wrong else ""))

    hotel_plans = hotels.generate(cfg)
    hotel_zones = {h.body["address"]["postalCode"][:5] for h in hotel_plans}
    streets = {z.postal_prefix: z.streets for z in geo.ZONES}
    outside = []
    for v in venues:
        address = found.get(v.id, {}).get("address", {})
        prefix = address.get("postalCode", "")[:5]
        if prefix not in hotel_zones or not address.get("streetAddress", "").startswith(streets.get(prefix, ())):
            outside.append(v.id)
    report(not outside, f"endereços em zonas com hotéis: {len(venues) - len(outside)}/{len(venues)}" + (f", fora: {outside}" if outside else ""))

    lonely = []
    for h in hotel_plans:
        lon, lat = h.body["location"]
        near = await client.get("/v1/restaurants", near=f"{lon},{lat}", maxDistance=2 * max(z.radius for z in geo.ZONES), limit=1000)
        if not any(r["id"].startswith(PREFIX) for r in near):
            lonely.append(h.id)
    report(not lonely, f"hotéis com restaurante a até 1,8 km: {len(hotel_plans) - len(lonely)}/{len(hotel_plans)}" + (f", sem: {lonely}" if lonely else ""))
    return ok


def kind_of(item: dict) -> str:
    category = item.get("category")
    values = category if isinstance(category, list) else [category]
    return "restaurant" if "restaurant" in values else "bar" if "bar" in values else ""
