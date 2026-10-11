"""Website route wiring for the ASGI app.

:func:`register_website_routes` mounts, in order:

1. the framework's own DB-backed website pages (``grunt/website/``),
2. ``/sitemap.xml`` and ``/robots.txt``,
3. ``/assets/grunt`` static files,
4. the ``/{path:path}`` catch-all - root static file -> server-side page ->
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
from grunt.config import settings
from grunt.site.manager import site_manager
from grunt.website import make_website_handler, robots_txt, sitemap_xml, website_registry
from grunt.website.router import PAGE_METHODS, render_not_found, render_page_by_route
from grunt.website.spa import DIST_DIR, static_file

if TYPE_CHECKING:
    from fastapi import FastAPI


_GRUNT_PKG = Path(__file__).resolve().parent.parent  # grunt/startup/website.py -> grunt/
_CORE_WEBSITE_DIR = _GRUNT_PKG / "website"
_MAIN_PUBLIC_DIR = _GRUNT_PKG.parent / "public"


# Top-level routes of the Desk SPA (frontend/src/router/index.ts) - the only
# paths that get the SPA shell when no server-side page claims them.
_SPA_ROUTES = (
    "/app",
    "/setup",
    "/login",
    "/signup",
    "/forgot-password",
    "/reset-password",
    "/mfa-verify",
    "/403",
)


def _is_spa_path(path: str) -> bool:
    path = path.rstrip("/") or "/"
    return path == "/" or any(path == r or path.startswith(r + "/") for r in _SPA_ROUTES)


async def _legacy_workspace_url(request: Request, session) -> str | None:
    """``/app/<path>`` for an old bare ``/<workspace>/...`` bookmark, else None.

    Under an app's own website prefix (``/<app>/...`` with www pages, where
    the workspace is often named after the app) only ``/<app>/<DocType>/...``
    is taken for a bookmark - the rest is that site's 404.
    """
    import grunt
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    first, _sep, rest = request.url.path.strip("/").partition("/")
    if not first:
        return None
    has_site = any(page.app == first for page in website_registry.pages)
    try:
        async with grunt.context(session, user=SYSTEM_USER):
            if not await grunt.db.exists("AppMenu", first):
                return None
            if has_site and await grunt.get_meta(rest.split("/", 1)[0]) is None:
                return None
    except Exception as e:  # noqa: BLE001 - a lookup failure must not turn a 404 into a 500
        log.warning("website.legacy_workspace.error", path=request.url.path, error=str(e))
        return None
    query = request.url.query
    return f"/app{request.url.path}" + (f"?{query}" if query else "")


def register_website_routes(app: FastAPI) -> None:
    for page in website_registry.discover_app(_CORE_WEBSITE_DIR, "grunt", is_main_app=True):
        app.add_api_route(
            page.url_pattern,
            make_website_handler(page),
            methods=PAGE_METHODS,
            include_in_schema=False,
            tags=["website"],
        )

    app.add_api_route(
        "/sitemap.xml",
        sitemap_xml,
        methods=["GET", "HEAD"],
        include_in_schema=False,
        tags=["website"],
    )
    app.add_api_route(
        "/robots.txt",
        robots_txt,
        methods=["GET", "HEAD"],
        include_in_schema=False,
        tags=["website"],
    )

    # NOTE: Do NOT mount StaticFiles at "/" - it would intercept all paths
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
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )


async def _website_catch_all(request: Request):
    """Dynamic DB pages: root static file -> server-side page -> SPA fallback."""
    from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

    # 1. Serve root-level static files (replaces a StaticFiles mount at "/").
    #    In production the built SPA (dist/) comes first - Vite serves it in dev.
    req_path = request.url.path.lstrip("/")
    if not settings.debug and (built := static_file(DIST_DIR, req_path)):
        # Vite content-hashes everything under assets/, so it never changes.
        immutable = req_path.startswith("assets/")
        return FileResponse(
            str(built),
            headers={"Cache-Control": "public, max-age=31536000, immutable"} if immutable else None,
        )
    if candidate := static_file(_MAIN_PUBLIC_DIR, req_path):
        return FileResponse(str(candidate))

    # 2. Try server-side website pages.
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session:
        response = await render_page_by_route(request, session)
        if response:
            return response

        # 3. Anything that is not a Desk route is a missing page, not the SPA
        #    shell with a 200 (a "soft 404" for search engines and a blank
        #    Desk for a reader of the public site).
        if not _is_spa_path(request.url.path):
            if workspace_url := await _legacy_workspace_url(request, session):
                return RedirectResponse(workspace_url, status_code=301)
            if response := await render_not_found(request, session):
                return response
            raise HTTPException(status_code=404, detail=_("Page not found"))

    # 4. A Desk route - the SPA shell, vue-router takes it from here.
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
