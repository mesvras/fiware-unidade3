import httpx

from .config import Settings
from .convert import normalize

ENTITIES = "/ngsi-ld/v1/entities"


class OrionUnavailable(Exception):
    pass


class OrionError(Exception):
    def __init__(self, status: int, body):
        self.status = status
        self.body = body
        super().__init__(f"Orion-LD respondeu {status}: {body}")


class Orion:
    def __init__(self, settings: Settings):
        headers = {"Link": f'<{settings.context_url}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'}
        if settings.tenant:
            headers["NGSILD-Tenant"] = settings.tenant
        self.client = httpx.AsyncClient(base_url=settings.orion_url, timeout=settings.timeout, headers=headers)

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return await self.client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            raise OrionUnavailable(str(e) or type(e).__name__) from e

    @staticmethod
    def _fail(r: httpx.Response):
        try:
            body = r.json()
        except ValueError:
            body = r.text
        raise OrionError(r.status_code, body)

    async def version(self) -> str:
        r = await self._send("GET", "/ngsi-ld/ex/v1/version")
        if r.status_code != 200:
            raise OrionUnavailable(f"HTTP {r.status_code}")
        return r.json().get("Orion-LD version", "")

    async def create(self, entity: dict) -> None:
        r = await self._send("POST", ENTITIES, json=entity)
        if r.status_code != 201:
            self._fail(r)

    async def get(self, entity_id: str) -> dict | None:
        r = await self._send("GET", f"{ENTITIES}/{entity_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            self._fail(r)
        return normalize(r.json())

    async def get_many(self, ids: list[str]) -> dict[str, dict]:
        found = {}
        for entity_id in dict.fromkeys(ids):
            e = await self.get(entity_id)
            if e is not None:
                found[entity_id] = e
        return found

    async def update(self, entity_id: str, attrs: dict) -> None:
        r = await self._send("PATCH", f"{ENTITIES}/{entity_id}/attrs", json=attrs)
        if r.status_code != 204:
            self._fail(r)

    async def delete(self, entity_id: str) -> bool:
        r = await self._send("DELETE", f"{ENTITIES}/{entity_id}")
        if r.status_code == 404:
            return False
        if r.status_code != 204:
            self._fail(r)
        return True

    async def query(self, params: dict) -> list[dict]:
        r = await self._send("GET", ENTITIES, params=params)
        if r.status_code != 200:
            self._fail(r)
        return [normalize(e) for e in r.json()]

    async def close(self) -> None:
        await self.client.aclose()
