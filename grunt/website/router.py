"""
Website page rendering engine - Enhanced routing for Grunt apps.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from grunt import log

# Grunt-level base templates directory (apps can extend _base.html from here)
_GRUNT_WWW_TEMPLATES_DIR = Path(__file__).parent / "templates"


class WebsitePage:
    """A single public web page discovered from an app's www/ directory."""

    def __init__(self, html_file: Path, www_dir: Path, app: str, url_pattern: str) -> None:
        self.html_file = html_file
        self.www_dir = www_dir
        self.app = app
        # FastAPI-style pattern, e.g. "/blog/{slug}"
        self.url_pattern = url_pattern

    @property
    def template_name(self) -> str:
        return str(self.html_file.relative_to(self.www_dir))

    @property
    def py_file(self) -> Path | None:
        f = self.html_file.with_suffix(".py")
        return f if f.exists() else None

    def __repr__(self) -> str:
        return f"<WebsitePage app={self.app!r} url={self.url_pattern!r}>"


class WebsiteRegistry:
    """Collects WebsitePage objects from all installed apps."""

    def __init__(self) -> None:
        self._pages: list[WebsitePage] = []
        # Jinja2 Environment per app name
        self._envs: dict[str, Environment] = {}

    def discover_app(
        self, app_dir: Path, app_name: str, is_main_app: bool = False
    ) -> list[WebsitePage]:
        """Scan app_dir/www/ for .html files and register pages."""
        www_dir = app_dir / "www"
        if not www_dir.is_dir():
            return []

        loaders: list[FileSystemLoader] = [FileSystemLoader(str(www_dir))]
        if _GRUNT_WWW_TEMPLATES_DIR.is_dir():
            loaders.append(FileSystemLoader(str(_GRUNT_WWW_TEMPLATES_DIR)))

        env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html"]),
            enable_async=True,
        )
        from grunt.i18n.jinja import install as install_i18n
        from grunt.website.block_types import get_block_template

        install_i18n(env)

        env.globals["block_template"] = get_block_template
        # {% set menu = website_menu("main") %} - WebsiteMenuItem tree (async, auto-awaited)
        from grunt.website.menu import get_menu

        env.globals["website_menu"] = get_menu
        from grunt.website.spa import spa_assets

        env.globals["spa_assets"] = spa_assets
        self._envs[app_name] = env

        discovered: list[WebsitePage] = []
        for html_file in sorted(www_dir.rglob("*.html")):
            if html_file.name.startswith("_"):
                continue  # skip base/partial templates (_base.html, _header.html …)

            rel_parts = list(html_file.relative_to(www_dir).parts)
            stem = rel_parts[-1][:-5]  # strip ".html"

            if stem == "index":
                rel_parts = rel_parts[:-1]
            else:
                rel_parts[-1] = stem

            # Routing Logic:
            # 1. Main app (grunt) pages are mounted at root: /login, /signup
            # 2. Other apps are mounted with prefix: /hrm/dashboard
            # 3. If a page is named 'index' in a subfolder, it takes the folder name

            if is_main_app:
                url_pattern = "/" + "/".join(rel_parts) if rel_parts else "/"
            else:
                url_pattern = (
                    "/" + "/".join([app_name] + rel_parts) if rel_parts else f"/{app_name}"
                )

            page = WebsitePage(html_file, www_dir, app_name, url_pattern)
            self._pages.append(page)
            discovered.append(page)
            log.debug("website.page.discovered", app=app_name, url=url_pattern)

        return discovered

    def get_env(self, app_name: str) -> Environment | None:
        return self._envs.get(app_name)

    def add_template_source(self, app_name: str, path: Path) -> None:
        """Append *path* as a template search directory for *app_name*'s env.

        Lets an installed app contribute templates (e.g. custom block-type
        renderers) that resolve inside another app's environment - used by
        external apps that register `website_block_types` in hooks.py but
        render through the shared "grunt" env.
        """
        env = self._envs.get(app_name)
        if env is None or not path.is_dir():
            return
        loader = env.loader
        if isinstance(loader, ChoiceLoader):
            loader.loaders = [*loader.loaders, FileSystemLoader(str(path))]

    @property
    def pages(self) -> list[WebsitePage]:
        return list(self._pages)


website_registry = WebsiteRegistry()


async def render_page(
    page: WebsitePage,
    request: Request,
    path_params: dict[str, Any] | None = None,
    *,
    session: Any,
) -> Response:
    """Load controller context, render the Jinja2 template, return the HTML page.

    A controller may return a ``Response`` instead of a context dict (e.g. a
    ``RedirectResponse``) - it is sent as is.
    """
    import grunt
    from grunt.config import settings

    context: dict[str, Any] = {
        "request": request,
        "path_params": path_params or {},
        "query_params": dict(request.query_params),
        "session": session,
        "title": "",
        "description": "",
        "dev_mode": settings.debug,
    }

    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with grunt.context(session, user=SYSTEM_USER):
        try:
            # Fetch global website settings (Singleton)
            ws = await grunt.get_doc("WebsiteSettings")
            context["website_settings"] = ws
        except Exception:
            context["website_settings"] = None

        # Controller errors propagate to the exception handlers (HTML error page):
        # rendering the template without the controller's context only turns
        # the real error into a misleading "'x' is undefined".
        if page.py_file:
            spec = importlib.util.spec_from_file_location("_www_controller", page.py_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[arg-type]

                # Handle POST logic if present
                if request.method == "POST" and hasattr(mod, "handle_post"):
                    result = mod.handle_post(context)
                    if inspect.isawaitable(result):
                        result = await result
                    # A returned response (e.g. a redirect) goes out as is.
                    if isinstance(result, Response):
                        return result
                    if isinstance(result, dict):
                        context.update(result)

                if hasattr(mod, "get_context"):
                    result = mod.get_context(context)
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, Response):  # e.g. RedirectResponse
                        return result
                    if isinstance(result, dict):
                        context.update(result)

    env = website_registry.get_env(page.app)
    if env is None:
        raise ValueError(f"No Jinja2 environment for app '{page.app}'")

    template_name = context.get("template_name") or page.template_name
    template = env.get_template(template_name)
    # Templates query too (website_menu) - render inside the grunt context.
    async with grunt.context(session, user=SYSTEM_USER):
        html = await template.render_async(**context)
    # A controller may set e.g. ``context["status_code"] = 404`` for a missing record.
    return HTMLResponse(content=html, status_code=context.get("status_code") or 200)


_PARAM_TOKEN_RE = re.compile(r"\{(\w+)\}")


def _pattern_regex(url_pattern: str) -> re.Pattern[str]:
    """Compile a ``/service/{route}``-style pattern to a matching regex.

    External apps' file-based pages reach FastAPI's own routing table only
    after ASGI lifespan startup (:func:`grunt.apps.loader.load_external_apps`)
    - which runs *after* the catch-all ``/{path:path}`` is already mounted at
    import time in :mod:`grunt.main`, so it always matches first and shadows
    them. This regex match is what actually resolves a dynamic file-based
    page for those apps; static patterns are still handled by the plain
    string comparison below (cheaper, and the common case).
    """
    parts: list[str] = []
    last = 0
    for m in _PARAM_TOKEN_RE.finditer(url_pattern):
        parts.append(re.escape(url_pattern[last : m.start()]))
        parts.append(f"(?P<{m.group(1)}>[^/]+)")
        last = m.end()
    parts.append(re.escape(url_pattern[last:]))
    return re.compile("^" + "".join(parts) + "$")


async def render_page_by_route(
    request: Request,
    session: Any,
) -> Response | None:
    """Try to render a page by its route, checking both files and database."""
    import grunt

    path = request.url.path
    # Clean trailing slash for matching
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # 1. Try file-based pages first - static routes by exact string, dynamic
    # ({param}) routes by regex (see _pattern_regex).
    for page in website_registry.pages:
        if page.url_pattern == path:
            return await render_page(page, request, session=session)

    for page in website_registry.pages:
        if "{" not in page.url_pattern:
            continue
        m = _pattern_regex(page.url_pattern).match(path)
        if m:
            return await render_page(page, request, m.groupdict(), session=session)

    # 2. Documents of web-view DocTypes (grunt.website.generator)
    from grunt.website.generator import render_doc_page

    try:
        response = await render_doc_page(request, session)
    except HTTPException:
        raise
    except Exception as e:
        log.warning("website.web_view.error", route=path, error=str(e))
        response = None
    if response is not None:
        return response

    # 3. Try database-based pages (WebPage)
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    try:
        async with grunt.context(session, user=SYSTEM_USER):
            pages = await grunt.db.get_all(
                "WebPage",
                filters={"route": path, "published": 1},
                limit=1,
            )
            if not pages:
                return None
            doc = await grunt.get_doc("WebPage", pages[0]["name"])
        return await render_db_page(doc, request, session=session)
    except HTTPException as exc:
        if exc.status_code == 404 and "DocType 'WebPage' not found" in str(exc.detail):
            return None
        log.warning("website.db_page.error", route=path, error=str(exc))
    except Exception as e:
        log.warning("website.db_page.error", route=path, error=str(e))

    return None


async def render_db_page(doc: dict[str, Any], request: Request, session: Any) -> HTMLResponse:
    """Render a dynamic page from the database using a generic template."""
    import grunt
    from grunt.config import settings

    context: dict[str, Any] = {
        "request": request,
        "doc": doc,
        "title": doc["title"],
        "description": doc.get("meta_description") or "",
        "content": doc.get("content"),
        "dev_mode": settings.debug,
    }

    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with grunt.context(session, user=SYSTEM_USER):
        try:
            ws = await grunt.get_doc("WebsiteSettings")
            context["website_settings"] = ws
        except Exception:
            context["website_settings"] = None

    # Use main app env for generic templates
    env = website_registry.get_env("grunt")
    if env is None:
        raise ValueError("No Jinja2 environment found")

    template = env.get_template("web_page.html")
    async with grunt.context(session, user=SYSTEM_USER):
        html = await template.render_async(**context)
    return HTMLResponse(content=html)


def make_website_handler(page: WebsitePage):
    """Return a FastAPI route handler for the given WebsitePage."""
    from grunt.db.session import get_session

    async def _handler(
        request: Request,
        session: Any = Depends(get_session),
    ) -> Response:
        return await render_page(page, request, dict(request.path_params) or None, session=session)

    safe = page.url_pattern.replace("/", "_").replace("{", "").replace("}", "")
    _handler.__name__ = f"website_{page.app}{safe}"
    return _handler


async def sitemap_xml(request: Request) -> Response:
    """Generate /sitemap.xml: www pages, published WebPage docs, web view documents."""
    import grunt
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.site.manager import site_manager
    from grunt.website.generator import sitemap_urls

    base = str(request.base_url).rstrip("/")

    urls = [
        base + page.url_pattern for page in website_registry.pages if "{" not in page.url_pattern
    ]

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.context(session, user=SYSTEM_USER):
        pages = await grunt.db.get_all(
            "WebPage",
            filters={"published": 1},
            fields=["route"],
            limit=None,
        )
        urls.extend(base + p["route"] for p in pages)
        urls.extend(base + url for url in await sitemap_urls())

    entries = "".join(f"  <url><loc>{url}</loc></url>\n" for url in urls)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}"
        "</urlset>"
    )
    return Response(content=body, media_type="application/xml")


async def robots_txt(request: Request) -> PlainTextResponse:
    """Generate /robots.txt pointing crawlers at the sitemap."""
    base = str(request.base_url).rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /app/\nSitemap: {base}/sitemap.xml\n"
    return PlainTextResponse(content=body)
