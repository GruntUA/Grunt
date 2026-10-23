"""``rate_limits`` in an app's hooks.py: a path with its own per-IP bucket.

A browser library (esign's euscp) calls a guest proxy dozens of times per
signature - the anonymous tier (30/min) cut it off mid-signing.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext
from grunt.middleware import rate_limit
from grunt.middleware.rate_limit import RateLimitMiddleware


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(rate_limit, "_PATH_LIMITS", {})
    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_anon", 2, raising=False)
    app = FastAPI()

    @app.get("/api/v1/method/demo.api.proxy")
    async def proxy() -> dict:
        return {"ok": True}

    @app.get("/api/v1/method/demo.api.other")
    async def other() -> dict:
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware)
    return TestClient(app)


def test_path_limit_replaces_anonymous_tier(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    HOOK_CONSUMERS["rate_limits"].apply(
        {"/api/v1/method/demo.api.proxy": 5}, LoadContext("demo", tmp_path)
    )

    codes = [client.get("/api/v1/method/demo.api.proxy").status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    # Its own bucket: the anonymous budget (2/min) is untouched by the proxy
    assert [client.get("/api/v1/method/demo.api.other").status_code for _ in range(3)] == [
        200,
        200,
        429,
    ]
