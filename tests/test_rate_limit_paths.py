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
    # Лічильники в пам'яті: у Redis кошики пережили б прогін і наступний за хвилину впав би.
    monkeypatch.setattr(rate_limit.shared, "get", lambda: None)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_anon", 2, raising=False)
    app = FastAPI()

    @app.get("/api/v1/method/demo.api.proxy")
    async def proxy() -> dict:
        return {"ok": True}

    @app.get("/api/v1/method/demo.api.other")
    async def other() -> dict:
        return {"ok": True}

    @app.get("/api/v1/app/demo/{rest:path}")
    async def app_api(rest: str) -> dict:
        return {"ok": rest}

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


def test_prefix_limit_shares_one_bucket(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    HOOK_CONSUMERS["rate_limits"].apply(
        {"/api/v1/app/demo/*": 4, "/api/v1/app/demo/download/big": 1}, LoadContext("demo", tmp_path)
    )
    paths = ["/api/v1/app/demo/api/3/action/package_show", "/api/v1/app/demo/download/x/a.csv"]
    codes = [client.get(paths[i % 2]).status_code for i in range(5)]
    assert codes == [200] * 4 + [429]  # один кошик на весь префікс, не 2/хв анонімних
    # Точний шлях — свій кошик, вужчий за префікс.
    assert [client.get("/api/v1/app/demo/download/big").status_code for _ in range(2)] == [200, 429]
    # Поза префіксом — звичайний анонімний ліміт.
    assert [client.get("/api/v1/method/demo.api.other").status_code for _ in range(3)] == [
        200,
        200,
        429,
    ]
