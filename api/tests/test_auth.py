import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid

import httpx
import pytest

from app.config import Settings

API_URL = os.environ.get("API_URL", "http://api:8000")
AUTH_URL = os.environ.get("API_AUTH_URL", "http://api-auth:8000")
IDP_URL = os.environ.get("IDP_URL", "http://test-idp:8080")
ISSUER, AUDIENCE = "http://test-idp/realms/natal", "natal-api"
DENIED = {"errors": ["não autenticado"]}
S = uuid.uuid4().hex[:8]


def claims(**over) -> dict:
    now = int(time.time())
    base = {"iss": ISSUER, "aud": AUDIENCE, "sub": "user-a", "iat": now, "exp": now + 300,
            "owner_id": "org-a", "realm_access": {"roles": ["hotelaria"]}}
    return {k: v for k, v in {**base, **over}.items() if v is not None}


def token(key: str = "k1", kid: str | None = "", **over) -> str:
    body = {"claims": claims(**over), "key": key}
    if kid != "":
        body["kid"] = kid
    return httpx.post(f"{IDP_URL}/token", json=body, timeout=10).json()["token"]


def b64(data: dict | bytes) -> str:
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def alg_none() -> str:
    return f"{b64({'alg': 'none', 'kid': 'k1'})}.{b64(claims())}."


def hs256_with_public_key() -> str:
    pem = httpx.get(f"{IDP_URL}/public.pem", timeout=10).content
    signing_input = f"{b64({'alg': 'HS256', 'kid': 'k1'})}.{b64(claims())}"
    signature = hmac.new(pem, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64(signature)}"


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=AUTH_URL, timeout=20) as client:
        yield client


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_health_is_public_and_terse(api):
    r = api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_are_closed(api):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert api.get(path).status_code == 404


def test_every_route_denies_without_token(api):
    spec = httpx.get(f"{API_URL}/openapi.json", timeout=10).json()
    checked = 0
    for path, operations in spec["paths"].items():
        if path == "/health":
            continue
        concrete = re.sub(r"\{[^}]+\}", "x", path)
        for method in operations:
            r = api.request(method.upper(), concrete, json={} if method in ("post", "patch") else None)
            assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
            assert r.headers["WWW-Authenticate"].startswith("Bearer")
            checked += 1
    assert checked >= 30


@pytest.mark.parametrize("make", [
    lambda: "abc",
    lambda: token(key="other", kid="k1"),
    alg_none,
    hs256_with_public_key,
    lambda: token(exp=int(time.time()) - 120),
    lambda: token(iat=int(time.time()) + 600),
    lambda: token(exp=None),
    lambda: token(iat=None),
    lambda: token(sub=None),
    lambda: token(iss="http://outro/realms/natal"),
    lambda: token(aud="outra-api"),
    lambda: token(kid="k9"),
    lambda: token(kid=None),
    lambda: token(owner_id="dono inválido"),
    lambda: token(padding="x" * 9000),
], ids=["lixo", "assinatura-de-outra-chave", "alg-none", "hs256-com-chave-publica", "expirado", "iat-no-futuro", "sem-exp", "sem-iat",
        "sem-sub", "iss-errado", "aud-errada", "kid-desconhecido", "sem-kid", "dono-invalido", "token-grande"])
def test_invalid_tokens_get_the_same_generic_401(api, make):
    r = api.get("/v1/hotels", headers=auth(make()))
    assert r.status_code == 401
    assert r.json() == DENIED
    assert r.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


def test_token_only_in_authorization_header(api):
    assert api.get("/v1/hotels", params={"access_token": token()}).status_code == 401
    assert api.get("/v1/hotels", headers={"Authorization": f"Basic {token()}"}).status_code == 401


def test_reader_can_read_but_not_write(api):
    reader = token(realm_access={"roles": []})
    assert api.get("/v1/hotels", headers=auth(reader)).status_code == 200
    assert api.post("/v1/hotels", json={}, headers=auth(reader)).status_code == 403


def test_role_is_per_resource(api):
    hotelier = token()
    assert api.post("/v1/events", json={}, headers=auth(hotelier)).status_code == 403
    assert api.post("/v1/beaches", json={}, headers=auth(hotelier)).status_code == 403
    assert api.delete("/v1/restaurants/x", headers=auth(hotelier)).status_code == 403


def test_owner_comes_from_token_and_guards_objects(api):
    owner_a, owner_b = auth(token()), auth(token(sub="user-b", owner_id="org-b"))
    colleague = auth(token(sub="user-a2", owner_id="org-a"))
    hid = f"teste-auth-{S}"
    body = {"id": hid, "name": "Hotel A", "location": [-35.2, -5.87], "address": {"addressLocality": "Natal"}, "dataOwner": "org-b"}
    room = {"id": "std", "name": "Std", "maxAdults": 2, "maxChildren": 0, "totalUnits": 2}
    try:
        r = api.post("/v1/hotels", json=body, headers=owner_a)
        assert r.status_code == 201
        assert r.json()["dataOwner"] == "org-a"
        assert api.patch(f"/v1/hotels/{hid}", json={"name": "Invadido"}, headers=owner_b).status_code == 403
        assert api.delete(f"/v1/hotels/{hid}", headers=owner_b).status_code == 403
        assert api.post(f"/v1/hotels/{hid}/room-types", json=room, headers=owner_b).status_code == 403
        assert api.patch(f"/v1/hotels/{hid}", json={"name": "Hotel A2"}, headers=colleague).status_code == 200
        assert api.post(f"/v1/hotels/{hid}/room-types", json=room, headers=owner_a).status_code == 201
        assert api.delete(f"/v1/hotels/{hid}/room-types/std", headers=owner_b).status_code == 403
        assert api.get(f"/v1/hotels/{hid}", headers=owner_b).json()["name"] == "Hotel A2"
    finally:
        api.delete(f"/v1/hotels/{hid}/room-types/std", headers=owner_a)
        api.delete(f"/v1/hotels/{hid}", headers=owner_a)


def test_owner_falls_back_to_subject(api):
    headers = auth(token(sub="user-sem-org", owner_id=None))
    hid = f"teste-auth-sub-{S}"
    try:
        r = api.post("/v1/hotels", json={"id": hid, "name": "H", "location": [-35.2, -5.87], "address": {"addressLocality": "Natal"}}, headers=headers)
        assert r.status_code == 201
        assert r.json()["dataOwner"] == "user-sem-org"
    finally:
        api.delete(f"/v1/hotels/{hid}", headers=headers)


def test_key_rotation_is_picked_up(api):
    assert api.get("/v1/hotels", headers=auth(token(key="k2"))).status_code == 401
    httpx.post(f"{IDP_URL}/rotate", timeout=10)
    time.sleep(1.5)
    assert api.get("/v1/hotels", headers=auth(token(key="k2"))).status_code == 200
    assert api.get("/v1/hotels", headers=auth(token(key="k1"))).status_code == 200


@pytest.mark.parametrize("over,expected", [
    ({"oidc_issuer": ""}, "OIDC_ISSUER não definido"),
    ({"oidc_audience": ""}, "OIDC_AUDIENCE não definido"),
    ({"oidc_jwks_url": ""}, "OIDC_JWKS_URL não definido"),
    ({"oidc_algorithms": ("HS256",)}, "recusados: HS256"),
    ({"oidc_algorithms": ("none",)}, "recusados: none"),
    ({"clock_skew": 600}, "JWT_CLOCK_SKEW_SECONDS"),
])
def test_unsafe_configuration_is_refused(over, expected):
    base = {"auth_enabled": True, "oidc_issuer": ISSUER, "oidc_audience": AUDIENCE, "oidc_jwks_url": f"{IDP_URL}/jwks.json"}
    assert Settings(**base).problems() == []
    assert any(expected in p for p in Settings(**{**base, **over}).problems())
