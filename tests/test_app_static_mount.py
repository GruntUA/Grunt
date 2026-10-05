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

from grunt.apps.loader import (
    LoadContext,
    _include_app_routers,
    _mount_app_static,
    _move_before_catch_all,
)

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


def test_app_router_routes_register_in_front_of_catch_all(tmp_path: Path) -> None:
    """Every route of an app's routes.py router must win over the catch-all."""
    import sys

    pkg = tmp_path / "demo_router_app" / "demo_router_app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "routes.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/demo_router_app')\n"
        "@router.get('/one')\n"
        "async def one() -> dict:\n"
        "    return {'route': 'one'}\n"
        "@router.get('/two/{name}')\n"
        "async def two(name: str) -> dict:\n"
        "    return {'route': name}\n"
    )

    fastapi_app = FastAPI()

    @fastapi_app.get("/{path:path}")
    async def catch_all(path: str) -> HTMLResponse:
        return HTMLResponse("spa")

    sys.path.insert(0, str(pkg.parent))
    try:
        _include_app_routers(
            LoadContext(app_name="demo_router_app", app_dir=pkg.parent, fastapi_app=fastapi_app)
        )
    finally:
        sys.path.remove(str(pkg.parent))
        sys.modules.pop("demo_router_app.routes", None)
        sys.modules.pop("demo_router_app", None)

    client = TestClient(fastapi_app)
    base = "/api/v1/app/demo_router_app/demo_router_app"
    assert client.get(f"{base}/one").json() == {"route": "one"}
    assert client.get(f"{base}/two/hello").json() == {"route": "hello"}
    assert fastapi_app.router.routes[-1].path == "/{path:path}"
