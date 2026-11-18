"""HTML vs JSON error responses (grunt.startup.errors)."""

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
    env = Environment(
        loader=DictLoader({"page.html": "<title>{{ settings.title }}</title>"}), autoescape=True
    )
    try:
        env.get_template("page.html").render()
    except UndefinedError as exc:
        return exc
    raise AssertionError("expected UndefinedError")


@pytest.fixture(autouse=True)
def _error_log(monkeypatch):
    """ErrorLog writes are stubbed: each records its status and gets an id."""
    written: list[int] = []

    async def _record(request, exc, http_status=500):
        written.append(http_status)
        return "ERR-1"

    monkeypatch.setattr(errors, "_persist_error_log", _record)
    return written


async def test_browser_gets_html_debug_page(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    resp = await errors._generic_exception(_request("/", "text/html,*/*"), _template_error())
    body = bytes(resp.body).decode()
    assert resp.status_code == 500
    assert resp.media_type == "text/html"
    assert "UndefinedError" in body
    # Where to read it - the ErrorLog record - not the text or traceback.
    assert "/ErrorLog/ERR-1" in body
    assert "is undefined" not in body
    assert "page.html" not in body


async def test_browser_gets_html_without_debug_details(monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    resp = await errors._generic_exception(_request("/", "text/html"), _template_error())
    body = bytes(resp.body).decode()
    assert resp.status_code == 500
    assert "UndefinedError" not in body
    assert "Traceback" not in body


async def test_api_keeps_json(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    resp = await errors._generic_exception(_request("/api/v1/x", "text/html"), _template_error())
    data = json.loads(bytes(resp.body))
    assert data["error"]["code"] == "INTERNAL_ERROR"
    assert data["error"]["debug"] == {
        "exc_type": "UndefinedError",
        "error_log": "ERR-1",
        "request_id": None,
    }


async def test_validation_error_in_debug_is_logged_and_referenced(monkeypatch, _error_log):
    from pydantic import BaseModel, ValidationError

    class Model(BaseModel):
        n: int

    with pytest.raises(ValidationError) as caught:
        Model(n="secret-input")  # pyright: ignore[reportArgumentType]
    validation = caught.value
    monkeypatch.setattr(settings, "debug", True)
    resp = await errors._validation_error(_request("/api/v1/x", "application/json"), validation)
    data = json.loads(bytes(resp.body))
    assert resp.status_code == 422
    assert data["error"]["debug"]["error_log"] == "ERR-1"
    assert "secret-input" not in bytes(resp.body).decode()
    assert _error_log == [422]

    monkeypatch.setattr(settings, "debug", False)
    resp = await errors._validation_error(_request("/api/v1/x", "application/json"), validation)
    assert "debug" not in json.loads(bytes(resp.body))["error"]
    assert _error_log == [422]  # client input mistakes are not logged


async def test_xhr_keeps_json():
    exc = HTTPException(status_code=404, detail="Nope")
    resp = await errors._http_exception(_request("/office/x", "application/json"), exc)
    assert json.loads(bytes(resp.body))["error"]["message"] == "Nope"


async def test_http_404_html():
    exc = HTTPException(status_code=404, detail="Office not found")
    resp = await errors._http_exception(_request("/office/x", "text/html"), exc)
    assert resp.status_code == 404
    assert "Office not found" in bytes(resp.body).decode()
