"""App ``public/`` assets must win over the website catch-all route.

External apps are loaded at lifespan startup — after grunt.startup.website
has already registered ``/{path:path}`` — so a plain ``app.mount`` landed
behind the catch-all and every ``/assets/<app>/...`` request got the SPA
shell (text/html) instead of the file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from grunt.apps.loader import LoadContext, _mount_app_static, _move_before_catch_all

if TYPE_CHECKING:
    from pathlib import Path


def test_app_assets_mount_in_front_of_catch_all(tmp_path: Path) -> None:
    app_dir = tmp_path / "demo_app"
    (app_dir / "public" / "css").mkdir(parents=True)
    (app_dir / "public" / "css" / "site.css").write_text("body{color:red}")

    fastapi_app = FastAPI()

    @fastapi_app.get("/{path:path}")
    async def catch_all(path: str) -> HTMLResponse:
        return HTMLResponse("<html>spa</html>")

    _mount_app_static(LoadContext(app_name="demo_app", app_dir=app_dir, fastapi_app=fastapi_app))

    response = TestClient(fastapi_app).get("/assets/demo_app/css/site.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert response.text == "body{color:red}"


def test_app_pages_register_in_front_of_catch_all() -> None:
    """Pages must hit their own route (committing get_session), not the catch-all."""
    fastapi_app = FastAPI()

    @fastapi_app.get("/{path:path}")
    async def catch_all(path: str) -> HTMLResponse:
        return HTMLResponse("spa")

    @fastapi_app.get("/demo_app/news/{route}")
    async def page(route: str) -> HTMLResponse:
        return HTMLResponse(f"news {route}")

    _move_before_catch_all(fastapi_app)

    assert TestClient(fastapi_app).get("/demo_app/news/hello").text == "news hello"
