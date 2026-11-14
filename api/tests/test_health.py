import os

import httpx

API_URL = os.environ.get("API_URL", "http://api:8000")


def test_health_reports_orion_version():
    r = httpx.get(f"{API_URL}/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["orion"]


def test_openapi_is_published():
    r = httpx.get(f"{API_URL}/openapi.json", timeout=10)
    assert r.status_code == 200
    assert "/health" in r.json()["paths"]
