import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    orion_url: str = os.environ.get("ORION_URL", "http://orion:1026")
    context_url: str = os.environ.get("CONTEXT_URL", "http://context/natal-context.jsonld")
    tenant: str = os.environ.get("NGSILD_TENANT", "")
    timeout: float = float(os.environ.get("ORION_TIMEOUT", "10"))
    dev_owner: str = os.environ.get("DEV_OWNER", "dev-owner")
    limited_ratio: float = float(os.environ.get("AVAILABILITY_LIMITED_RATIO", "0.7"))
    auth_enabled: bool = os.environ.get("AUTH_ENABLED", "false").lower() == "true"


settings = Settings()
