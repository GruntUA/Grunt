"""HTML vs JSON error responses (grunt.startup.errors)."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from jinja2 import DictLoader, Environment, UndefinedError
from starlette.requests import Request

from grunt.config import settings
from grunt.startup import errors


def _request(path: str, accept: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [(b"accept", accept.encode()), (b"host", b"test")],
            "scheme": "http",
            "server": ("test", 80),
            "state": {},
        }
    )


def _template_error() -> UndefinedError:
    env = Environment(loader=DictLoader({"page.html": "<title>{{ settings.title }}</title>"}))
    try:
        env.get_template("page.html").render()
    except UndefinedError as exc:
        return exc
    raise AssertionError("expected UndefinedError")


@pytest.fixture(autouse=True)
def _no_error_log(monkeypatch):
    async def _noop(request, exc):
        return None

    monkeypatch.setattr(errors, "_persist_error_log", _noop)


async def test_browser_gets_html_debug_page(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    resp = await errors._generic_exception(_request("/", "text/html,*/*"), _template_error())
    body = resp.body.decode()
    assert resp.status_code == 500
    assert resp.media_type == "text/html"
    assert "UndefinedError" in body
    assert "&#39;settings&#39; is undefined" in body
    # The offending template line is pinpointed.
    assert "page.html" in body


async def test_browser_gets_html_without_debug_details(monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    resp = await errors._generic_exception(_request("/", "text/html"), _template_error())
    body = resp.body.decode()
    assert resp.status_code == 500
    assert "UndefinedError" not in body
    assert "Traceback" not in body


async def test_api_keeps_json(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    resp = await errors._generic_exception(_request("/api/v1/x", "text/html"), _template_error())
    data = json.loads(bytes(resp.body))
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert data["error"]["debug"]["exc_type"] == "UndefinedError"
    assert "Exception Group" not in data["error"]["debug"]["traceback"]


async def test_xhr_keeps_json():
    exc = HTTPException(status_code=404, detail="Nope")
    resp = await errors._http_exception(_request("/office/x", "application/json"), exc)
    assert json.loads(bytes(resp.body))["error"]["message"] == "Nope"


async def test_http_404_html():
    exc = HTTPException(status_code=404, detail="Office not found")
    resp = await errors._http_exception(_request("/office/x", "text/html"), exc)
    assert resp.status_code == 404
    assert "Office not found" in resp.body.decode()
