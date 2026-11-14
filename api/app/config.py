import os
from dataclasses import dataclass, field

SAFE_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"})


def _list(name: str, default: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.environ.get(name, default).split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    orion_url: str = os.environ.get("ORION_URL", "http://orion:1026")
    context_url: str = os.environ.get("CONTEXT_URL", "http://context/natal-context.jsonld")
    tenant: str = os.environ.get("NGSILD_TENANT", "")
    timeout: float = float(os.environ.get("ORION_TIMEOUT", "10"))
    dev_owner: str = os.environ.get("DEV_OWNER", "dev-owner")
    limited_ratio: float = float(os.environ.get("AVAILABILITY_LIMITED_RATIO", "0.7"))
    auth_enabled: bool = os.environ.get("AUTH_ENABLED", "true").lower() != "false"
    oidc_issuer: str = os.environ.get("OIDC_ISSUER", "")
    oidc_audience: str = os.environ.get("OIDC_AUDIENCE", "")
    oidc_jwks_url: str = os.environ.get("OIDC_JWKS_URL", "")
    oidc_algorithms: tuple[str, ...] = field(default_factory=lambda: _list("OIDC_ALGORITHMS", "RS256"))
    owner_claim: str = os.environ.get("OWNER_CLAIM", "owner_id")
    clock_skew: int = int(os.environ.get("JWT_CLOCK_SKEW_SECONDS", "30"))
    jwks_cache_seconds: int = int(os.environ.get("JWKS_CACHE_SECONDS", "300"))
    jwks_min_refresh_seconds: int = int(os.environ.get("JWKS_MIN_REFRESH_SECONDS", "30"))
    max_token_bytes: int = int(os.environ.get("MAX_TOKEN_BYTES", "8192"))

    def problems(self) -> list[str]:
        if not self.auth_enabled:
            return []
        found = [f"{name} não definido" for name, v in (("OIDC_ISSUER", self.oidc_issuer), ("OIDC_AUDIENCE", self.oidc_audience),
                                                         ("OIDC_JWKS_URL", self.oidc_jwks_url)) if not v]
        if not self.oidc_algorithms:
            found.append("OIDC_ALGORITHMS vazio")
        unsafe = [a for a in self.oidc_algorithms if a not in SAFE_ALGORITHMS]
        if unsafe:
            found.append(f"OIDC_ALGORITHMS só aceita algoritmos assimétricos; recusados: {', '.join(unsafe)}")
        if not 0 <= self.clock_skew <= 120:
            found.append("JWT_CLOCK_SKEW_SECONDS deve ficar entre 0 e 120")
        return found


settings = Settings()
