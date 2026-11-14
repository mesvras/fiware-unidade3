import logging
import re
import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, settings
from .errors import ApiError

log = logging.getLogger("app.auth")

ROLES = ("hotelaria", "bares-restaurantes", "produtor-cultural", "gestor-governo")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub"]
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{3,64}$")


@dataclass(frozen=True)
class Principal:
    subject: str
    owner: str
    roles: frozenset[str]


class AuthFailed(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class AuthUnavailable(Exception):
    pass


class Jwks:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.keys: dict[str, jwt.PyJWK] = {}
        self.loaded_at = 0.0
        self.client = httpx.AsyncClient(timeout=5, follow_redirects=False)

    async def _load(self) -> None:
        try:
            r = await self.client.get(self.cfg.oidc_jwks_url)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise AuthUnavailable(f"JWKS indisponível: {type(e).__name__}") from e
        keys = {}
        for raw in data.get("keys", []) if isinstance(data, dict) else []:
            if not isinstance(raw, dict) or not raw.get("kid") or raw.get("use", "sig") != "sig":
                continue
            try:
                keys[raw["kid"]] = jwt.PyJWK(raw)
            except jwt.PyJWKError:
                log.warning("chave do JWKS ignorada: kid=%s", raw.get("kid"))
        self.keys = keys
        self.loaded_at = time.monotonic()

    async def key(self, kid: str) -> jwt.PyJWK | None:
        age = time.monotonic() - self.loaded_at
        if not self.loaded_at or age > self.cfg.jwks_cache_seconds:
            await self._load()
        elif kid not in self.keys and age > self.cfg.jwks_min_refresh_seconds:
            await self._load()
        return self.keys.get(kid)

    async def close(self) -> None:
        await self.client.aclose()


class Verifier:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.jwks = Jwks(cfg)

    async def verify(self, token: str) -> Principal:
        if len(token.encode()) > self.cfg.max_token_bytes:
            raise AuthFailed("token maior que o limite")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.DecodeError:
            raise AuthFailed("cabeçalho do token inválido")
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in self.cfg.oidc_algorithms:
            raise AuthFailed(f"algoritmo não permitido: {alg}")
        if not isinstance(kid, str) or not kid:
            raise AuthFailed("token sem kid")
        key = await self.jwks.key(kid)
        if key is None:
            raise AuthFailed(f"kid desconhecido: {kid}")
        if key.algorithm_name and key.algorithm_name != alg:
            raise AuthFailed("algoritmo do token difere do algoritmo da chave")
        try:
            claims = jwt.decode(token, key=key.key, algorithms=[alg], audience=self.cfg.oidc_audience, issuer=self.cfg.oidc_issuer,
                                leeway=self.cfg.clock_skew, options={"require": REQUIRED_CLAIMS, "verify_iat": True})
        except jwt.ExpiredSignatureError:
            raise AuthFailed("token expirado")
        except jwt.InvalidTokenError as e:
            raise AuthFailed(f"token inválido: {type(e).__name__}")
        return principal_from(claims, self.cfg.owner_claim)

    async def close(self) -> None:
        await self.jwks.close()


def principal_from(claims: dict, owner_claim: str) -> Principal:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthFailed("sub inválido")
    owner = claims.get(owner_claim) or subject
    if not isinstance(owner, str) or not OWNER_PATTERN.match(owner):
        raise AuthFailed("identificador do dono inválido")
    access = claims.get("realm_access")
    roles = access.get("roles", []) if isinstance(access, dict) else []
    return Principal(subject=subject, owner=owner, roles=frozenset(r for r in roles if isinstance(r, str)))


bearer = HTTPBearer(auto_error=False)


def dev_principal() -> Principal:
    return Principal(subject=settings.dev_owner, owner=settings.dev_owner, roles=frozenset(ROLES))


async def authenticate(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if not settings.auth_enabled:
        principal = dev_principal()
    else:
        if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
            raise ApiError(401, "não autenticado", headers={"WWW-Authenticate": "Bearer"})
        try:
            principal = await request.app.state.verifier.verify(credentials.credentials)
        except AuthFailed as e:
            log.warning("autenticação recusada: %s; rota=%s %s", e.reason, request.method, request.url.path)
            raise ApiError(401, "não autenticado", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
        except AuthUnavailable as e:
            log.error("autenticação indisponível: %s", e)
            raise ApiError(503, "autenticação indisponível")
    request.state.principal = principal
    return principal


def writer(role: str):
    async def check(request: Request, principal: Principal = Depends(authenticate)) -> None:
        if request.method not in SAFE_METHODS and role not in principal.roles:
            log.warning("acesso negado por papel: exige %s; dono=%s; rota=%s %s", role, principal.owner, request.method, request.url.path)
            raise ApiError(403, "acesso negado")
    return check


def ensure_owner(entity: dict, principal: Principal) -> None:
    owner = entity.get("dataOwner", {}).get("value")
    if owner != principal.owner:
        log.warning("acesso negado por dono: registro=%s; dono=%s", entity.get("id"), principal.owner)
        raise ApiError(403, "acesso negado")
