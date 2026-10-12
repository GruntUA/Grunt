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


def test_csp_follows_frame_options() -> None:
    client = _client()
    assert "frame-ancestors 'none'" in client.get("/plain").headers["content-security-policy"]
    framed = client.get("/framed").headers["content-security-policy"]
    assert "frame-ancestors 'self'" in framed
    assert "object-src 'none'" in framed


def test_hsts_only_over_https() -> None:
    assert "strict-transport-security" not in _client().get("/plain").headers
    https = TestClient(_client().app, base_url="https://testserver")
    assert https.get("/plain").headers["strict-transport-security"].startswith("max-age=")


def test_hsts_sent_behind_tls_terminating_proxy() -> None:
    # nginx -> uvicorn: the request is plain HTTP but X-Forwarded-Proto says https.
    resp = _client().get("/plain", headers={"x-forwarded-proto": "https"})
    assert resp.headers["strict-transport-security"].startswith("max-age=")


def test_hsts_absent_when_forwarded_proto_is_http() -> None:
    resp = _client().get("/plain", headers={"x-forwarded-proto": "http"})
    assert "strict-transport-security" not in resp.headers
