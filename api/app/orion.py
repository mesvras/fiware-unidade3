import httpx

from .config import Settings


class OrionUnavailable(Exception):
    pass


class Orion:
    def __init__(self, settings: Settings):
        headers = {"NGSILD-Tenant": settings.tenant} if settings.tenant else {}
        self.client = httpx.AsyncClient(base_url=settings.orion_url, timeout=settings.timeout, headers=headers)

    async def version(self) -> str:
        try:
            r = await self.client.get("/ngsi-ld/ex/v1/version")
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise OrionUnavailable(str(e) or type(e).__name__) from e
        return r.json().get("Orion-LD version", "")

    async def close(self) -> None:
        await self.client.aclose()
