"""SecurityHeadersMiddleware sets defaults — an endpoint's own header wins."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from grunt.middleware.security import SecurityHeadersMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/plain")
    async def plain() -> dict:
        return {}

    @app.get("/framed")
    async def framed() -> Response:
        return Response("x", headers={"X-Frame-Options": "SAMEORIGIN"})

    return TestClient(app)


def test_defaults_applied() -> None:
    headers = _client().get("/plain").headers
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_endpoint_header_not_overwritten() -> None:
    headers = _client().get("/framed").headers
    assert headers["x-frame-options"] == "SAMEORIGIN"
    assert headers["x-content-type-options"] == "nosniff"
