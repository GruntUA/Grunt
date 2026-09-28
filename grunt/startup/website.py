"""Website route wiring for the ASGI app.

:func:`register_website_routes` mounts, in order:

1. the framework's own DB-backed website pages (``grunt/website/``),
2. ``/sitemap.xml`` and ``/robots.txt``,
3. ``/assets/grunt`` static files,
4. the ``/{path:path}`` catch-all — root static file → server-side page →
   SPA fallback.

The catch-all must be registered last (after every router and app page), so
this is called at the very end of :mod:`grunt.main`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from fastapi.staticfiles import StaticFiles

from grunt import _, log
from grunt.website import make_website_handler, robots_txt, sitemap_xml, website_registry

if TYPE_CHECKING:
    from fastapi import FastAPI


_GRUNT_PKG = Path(__file__).resolve().parent.parent  # grunt/startup/website.py -> grunt/
_CORE_WEBSITE_DIR = _GRUNT_PKG / "website"
_MAIN_PUBLIC_DIR = _GRUNT_PKG.parent / "public"


def register_website_routes(app: FastAPI) -> None:
    for page in website_registry.discover_app(_CORE_WEBSITE_DIR, "grunt", is_main_app=True):
        app.add_api_route(
            page.url_pattern,
            make_website_handler(page),
            methods=["GET", "POST"],
            include_in_schema=False,
            tags=["website"],
        )

    app.add_api_route(
        "/sitemap.xml", sitemap_xml, methods=["GET"], include_in_schema=False, tags=["website"]
    )
    app.add_api_route(
        "/robots.txt", robots_txt, methods=["GET"], include_in_schema=False, tags=["website"]
    )

    # NOTE: Do NOT mount StaticFiles at "/" — it would intercept all paths
    # (including SPA routes like /403) and return its own 404 before the
    # catch-all ever runs. Root-level static files are served in the catch-all.
    if _MAIN_PUBLIC_DIR.is_dir():
        app.mount(
            "/assets/grunt",
            StaticFiles(directory=str(_MAIN_PUBLIC_DIR)),
            name="assets_grunt",
        )

    app.add_api_route(
        "/{path:path}",
        _website_catch_all,
        methods=["GET"],
        include_in_schema=False,
    )


async def _website_catch_all(request: Request):
    """Dynamic DB pages: root static file → server-side page → SPA fallback."""
    from fastapi.responses import FileResponse, HTMLResponse

    from grunt.config import settings
    from grunt.site.manager import site_manager
    from grunt.website.router import render_page_by_route

    # 1. Serve root-level static files (replaces a StaticFiles mount at "/").
    req_path = request.url.path.lstrip("/")
    if req_path:  # ignore "/" itself
        candidate = _MAIN_PUBLIC_DIR / req_path
        if candidate.is_file():
            return FileResponse(str(candidate))

    # 2. Try server-side website pages.
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session:
        response = await render_page_by_route(request, session)
        if response:
            return response

    # 3. No server-side page — fall back to the SPA so vue-router handles the
    #    path (covers /403, /app/*, and any other frontend route).
    env = website_registry.get_env("grunt")
    if env is not None:
        try:
            template = env.get_template("_spa.html")
            html = await template.render_async(
                request=request, title="Ґрунт", dev_mode=settings.debug
            )
            return HTMLResponse(content=html)
        except Exception as _exc:
            log.warning("website.spa_fallback.error", path=request.url.path, error=str(_exc))

    raise HTTPException(status_code=404, detail=_("Page not found"))
