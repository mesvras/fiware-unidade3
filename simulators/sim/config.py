import os
from dataclasses import dataclass
from datetime import UTC, date, datetime


def _int(name: str, default: int, minimum: int = 0) -> int:
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name}: valor mínimo é {minimum}")
    return value


@dataclass(frozen=True)
class Config:
    api_url: str
    seed: str
    start_date: date
    concurrency: int
    interval: int
    hotels: int
    nights: int
    restaurants: int = 25
    bars: int = 15
    events: int = 40
    event_days: int = 60
    stations: int = 2
    beaches: int = 6
    points_per_beach: int = 2

    @classmethod
    def from_env(cls) -> "Config":
        start = os.environ.get("SIM_START_DATE")
        return cls(
            api_url=os.environ.get("API_URL", "http://api:8000"),
            seed=os.environ.get("SIM_SEED", "natal"),
            start_date=date.fromisoformat(start) if start else datetime.now(UTC).date(),
            concurrency=_int("SIM_CONCURRENCY", 8, 1),
            interval=_int("SIM_INTERVAL", 30, 1),
            hotels=_int("SIM_HOTELS", 12),
            nights=_int("SIM_NIGHTS", 60, 1),
            restaurants=_int("SIM_RESTAURANTS", 25),
            bars=_int("SIM_BARS", 15),
            events=_int("SIM_EVENTS", 40),
            event_days=_int("SIM_EVENT_DAYS", 60, 7),
            stations=_int("SIM_STATIONS", 2, 1),
            beaches=_int("SIM_BEACHES", 6),
            points_per_beach=_int("SIM_POINTS_PER_BEACH", 2),
        )
