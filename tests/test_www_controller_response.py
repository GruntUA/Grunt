"""A www/ page controller may return a Response (e.g. a redirect) instead of a context."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.requests import Request

from grunt.website.router import WebsiteRegistry, render_page, website_registry

if TYPE_CHECKING:
    from pathlib import Path


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("test", 80),
            "root_path": "",
        }
    )


@pytest.mark.asyncio
async def test_controller_redirect_is_returned_as_is(ctx, tmp_path: Path, monkeypatch) -> None:
    www = tmp_path / "demo_www_app" / "www"
    www.mkdir(parents=True)
    (www / "go.html").write_text("<p>{{ message }}</p>")
    (www / "go.py").write_text(
        "from starlette.responses import RedirectResponse\n"
        "async def get_context(context):\n"
        "    if context['query_params'].get('away'):\n"
        "        return RedirectResponse('/elsewhere', status_code=302)\n"
        "    return {'message': 'stayed'}\n"
    )
    registry = WebsiteRegistry()
    (page,) = registry.discover_app(www.parent, "demo_www_app")
    monkeypatch.setattr(website_registry, "_envs", registry._envs)

    session = ctx.db._session()
    stay = await render_page(page, _request("/demo_www_app/go"), session=session)
    assert stay.status_code == 200
    assert b"stayed" in stay.body

    away_request = _request("/demo_www_app/go")
    away_request.scope["query_string"] = b"away=1"
    away = await render_page(page, away_request, session=session)
    assert away.status_code == 302
    assert away.headers["location"] == "/elsewhere"
