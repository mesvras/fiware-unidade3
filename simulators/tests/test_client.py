import asyncio
import json

import httpx

from sim.client import RETRIES, ApiClient


def run_with(handler, action):
    async def go():
        async with ApiClient("http://api", transport=httpx.MockTransport(handler), backoff=0) as client:
            return await action(client), client.failures
    return asyncio.run(go())


def test_upsert_creates_with_post():
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(201, json={})

    ok, failures = run_with(handler, lambda c: c.upsert("/v1/hotels", "/v1/hotels/h", {"id": "h", "name": "H"}))
    assert ok and failures == 0
    assert calls == ["POST"]


def test_upsert_patches_without_frozen_fields_on_conflict():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(409 if request.method == "POST" else 200, json={})

    body = {"roomType": "std", "stayDate": "2026-12-01", "availableUnits": 3}
    ok, _ = run_with(handler, lambda c: c.upsert("/v1/hotels/h/availability", "/v1/hotels/h/availability/std/2026-12-01",
                                                 body, frozen=("roomType", "stayDate")))
    assert ok
    assert calls[1] == ("PATCH", "/v1/hotels/h/availability/std/2026-12-01", {"availableUnits": 3})


def test_retries_on_503_and_network_error():
    replies = iter([httpx.ConnectError("sem rede"), httpx.Response(503), httpx.Response(201, json={})])

    def handler(request):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    ok, failures = run_with(handler, lambda c: c.upsert("/v1/hotels", "/v1/hotels/h", {"id": "h"}))
    assert ok and failures == 0


def test_gives_up_after_retries_and_counts_failure():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    ok, failures = run_with(handler, lambda c: c.upsert("/v1/hotels", "/v1/hotels/h", {"id": "h"}))
    assert not ok and failures == 1
    assert len(calls) == RETRIES


def test_client_error_counts_failure_without_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"errors": ["inválido"]})

    ok, failures = run_with(handler, lambda c: c.patch("/v1/hotels/h", {"name": ""}))
    assert not ok and failures == 1
    assert len(calls) == 1
