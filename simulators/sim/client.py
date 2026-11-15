import asyncio
import logging

import httpx

log = logging.getLogger("sim")

RETRIES = 5
BACKOFF = 0.5


class RequestFailed(Exception):
    pass


class ApiClient:
    def __init__(self, base_url: str, concurrency: int = 8, transport: httpx.AsyncBaseTransport | None = None,
                 backoff: float = BACKOFF):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=30, transport=transport)
        self._limit = asyncio.Semaphore(concurrency)
        self._backoff = backoff
        self.failures = 0

    async def __aenter__(self) -> "ApiClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with self._limit:
            for attempt in range(RETRIES):
                try:
                    response = await self._http.request(method, path, **kwargs)
                    if response.status_code != 503:
                        return response
                    reason = "503"
                except httpx.TransportError as e:
                    reason = type(e).__name__
                if attempt < RETRIES - 1:
                    await asyncio.sleep(self._backoff * 2 ** attempt)
            raise RequestFailed(f"{method} {path}: {reason} após {RETRIES} tentativas")

    async def get(self, path: str, **params) -> list | dict:
        response = await self.request("GET", path, params=params)
        if response.status_code != 200:
            raise RequestFailed(f"GET {path}: {response.status_code} {response.text}")
        return response.json()

    async def upsert(self, post_path: str, item_path: str, body: dict, frozen: tuple[str, ...] = ("id",)) -> bool:
        try:
            response = await self.request("POST", post_path, json=body)
            if response.status_code == 409:
                patch = {k: v for k, v in body.items() if k not in frozen}
                response = await self.request("PATCH", item_path, json=patch)
        except RequestFailed as e:
            return self._fail(str(e))
        if response.status_code not in (200, 201):
            return self._fail(f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text}")
        return True

    async def patch(self, path: str, body: dict) -> bool:
        try:
            response = await self.request("PATCH", path, json=body)
        except RequestFailed as e:
            return self._fail(str(e))
        if response.status_code != 200:
            return self._fail(f"PATCH {path}: {response.status_code} {response.text}")
        return True

    def _fail(self, message: str) -> bool:
        self.failures += 1
        log.error(message)
        return False
