import math
import random
from dataclasses import dataclass

METERS_PER_DEGREE = 111_320


@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    center: tuple[float, float]
    radius: int
    coastal: bool
    postal_prefix: str
    streets: tuple[str, ...]


ZONES = (
    Zone("orla-sul", "Orla Sul", (-35.1795, -5.8790), 900, True, "59091",
         ("Avenida das Gaivotas", "Rua dos Corais", "Rua Maré Alta", "Travessa do Farol Velho")),
    Zone("orla-central", "Orla Central", (-35.1890, -5.8420), 800, True, "59092",
         ("Avenida Beira Mar Leste", "Rua das Jangadas", "Rua Areia Branca", "Rua dos Pescadores")),
    Zone("centro-historico", "Centro Histórico", (-35.2075, -5.7930), 600, False, "59093",
         ("Rua do Sobrado Azul", "Rua da Matriz Antiga", "Praça dos Tecelões", "Rua do Mercado Velho")),
    Zone("bairro-universitario", "Bairro Universitário", (-35.2010, -5.8380), 700, False, "59094",
         ("Avenida dos Estudantes", "Rua das Bibliotecas", "Rua do Observatório", "Rua dos Ipês")),
    Zone("orla-norte", "Orla Norte", (-35.2105, -5.7480), 900, True, "59095",
         ("Avenida dos Coqueirais", "Rua da Barra", "Rua das Marisqueiras", "Rua Vento Leste")),
)


def point(rng: random.Random, zone: Zone) -> list[float]:
    lon, lat = zone.center
    distance = zone.radius * math.sqrt(rng.random())
    angle = rng.uniform(0, 2 * math.pi)
    dlat = distance * math.sin(angle) / METERS_PER_DEGREE
    dlon = distance * math.cos(angle) / (METERS_PER_DEGREE * math.cos(math.radians(lat)))
    return [round(lon + dlon, 6), round(lat + dlat, 6)]


def address(rng: random.Random, zone: Zone) -> dict:
    return {
        "streetAddress": f"{rng.choice(zone.streets)}, {rng.randint(10, 1999)}, {zone.name}",
        "postalCode": f"{zone.postal_prefix}-{rng.randint(0, 999):03d}",
        "addressLocality": "Natal",
        "addressRegion": "RN",
        "addressCountry": "BR",
    }


def distance_m(a: list[float], b: tuple[float, float]) -> float:
    dlat = (a[1] - b[1]) * METERS_PER_DEGREE
    dlon = (a[0] - b[0]) * METERS_PER_DEGREE * math.cos(math.radians(b[1]))
    return math.hypot(dlat, dlon)
