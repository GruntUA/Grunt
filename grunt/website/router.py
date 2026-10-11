"""
Website page rendering engine - Enhanced routing for Grunt apps.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from grunt import log

if TYPE_CHECKING:
    from types import ModuleType

# www/*.py controllers by path: (mtime, module)
_controllers: dict[Path, tuple[float, ModuleType]] = {}

# GET pages answer HEAD too (uptime monitors, link checkers, some crawlers).
PAGE_METHODS = ["GET", "HEAD", "POST"]

# Grunt-level base templates directory (apps can extend _base.html from here)
_GRUNT_WWW_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Extension points an app (the CMS) fills from hooks.py - see grunt.apps.consumers:
# template dirs searched before the core templates, Jinja globals, context
# processors run for every page and resolvers for paths no file page claims.
_template_dirs: list[Path] = []
_template_globals: dict[str, Any] = {}
_context_processors: list[Any] = []
_page_resolvers: list[Any] = []


def register_context_processor(fn: Any) -> None:
    """``async fn(context) -> dict | None`` - adds to every page's context."""
    if fn not in _context_processors:
        _context_processors.append(fn)


def register_page_resolver(fn: Any) -> None:
    """``async fn(request, session) -> Response | None`` - serves a path that no
    www page or web view claims (a CMS page, a redirect). It opens its own
    grunt context, like :func:`grunt.website.generator.render_doc_page`."""
    if fn not in _page_resolvers:
        _page_resolvers.append(fn)


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

    def controller(self) -> ModuleType | None:
        """The page's ``.py`` module - loaded once, reloaded when the file changes."""
        py = self.py_file
        if py is None:
            return None
        mtime = py.stat().st_mtime
        cached = _controllers.get(py)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        spec = importlib.util.spec_from_file_location("_www_controller", py)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _controllers[py] = (mtime, mod)
        return mod

    @property
    def in_sitemap(self) -> bool:
        """Static pages are listed unless the controller says ``sitemap = False``
        (redirects, sign-in, per-visitor pages)."""
        if "{" in self.url_pattern:
            return False
        mod = self.controller()
        return getattr(mod, "sitemap", True) is not False

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
        loaders.extend(FileSystemLoader(str(d)) for d in _template_dirs)
        if _GRUNT_WWW_TEMPLATES_DIR.is_dir():
            loaders.append(FileSystemLoader(str(_GRUNT_WWW_TEMPLATES_DIR)))

        env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html"]),
            enable_async=True,
        )
        from grunt.i18n.jinja import install as install_i18n

        install_i18n(env)

        from grunt.website.spa import spa_assets

        env.globals["spa_assets"] = spa_assets
        # <img src="{{ image_url(doc.image, 960) }}" srcset="{{ image_srcset(doc.image) }}">
        from grunt.storage.files import image_srcset, sized_url

        env.globals["image_url"] = sized_url
        env.globals["image_srcset"] = image_srcset
        env.globals.update(_template_globals)
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

    def add_template_dir(self, path: Path) -> None:
        """Search *path* before the core templates in every app's env - an app's
        ``_base.html`` there becomes the site layout of apps without their own."""
        if not path.is_dir() or path in _template_dirs:
            return
        _template_dirs.append(path)
        for env in self._envs.values():
            loader = env.loader
            if isinstance(loader, ChoiceLoader):
                loader.loaders = [
                    *loader.loaders[:-1],
                    FileSystemLoader(str(path)),
                    loader.loaders[-1],
                ]

    def add_global(self, name: str, value: Any) -> None:
        """A Jinja global in every app's env (``website_menu`` of the CMS)."""
        _template_globals[name] = value
        for env in self._envs.values():
            env.globals[name] = value

    @property
    def pages(self) -> list[WebsitePage]:
        return list(self._pages)


website_registry = WebsiteRegistry()


async def page_context(request: Request, session: Any, **extra: Any) -> dict[str, Any]:
    """The context every page starts from, context processors applied (the
    caller holds a grunt context)."""
    from grunt.config import settings
    from grunt.site.settings import get_setting

    context: dict[str, Any] = {
        "request": request,
        "path_params": {},
        "query_params": dict(request.query_params),
        "session": session,
        "title": "",
        "description": "",
        "dev_mode": settings.debug,
        "site_name": await get_setting("app_name") or "Ґрунт",
        "site_logo": await get_setting("app_logo"),
        **extra,
    }
    for processor in _context_processors:
        result = processor(context)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            context.update(result)
    return context


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
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with grunt.context(session, user=SYSTEM_USER):
        context = await page_context(request, session, path_params=path_params or {})

        # Controller errors propagate to the exception handlers (HTML error page):
        # rendering the template without the controller's context only turns
        # the real error into a misleading "'x' is undefined".
        mod = page.controller()
        # Handle POST logic if present
        if mod is not None and request.method == "POST" and hasattr(mod, "handle_post"):
            result = mod.handle_post(context)
            if inspect.isawaitable(result):
                result = await result
            # A returned response (e.g. a redirect) goes out as is.
            if isinstance(result, Response):
                return result
            if isinstance(result, dict):
                context.update(result)

        if mod is not None and hasattr(mod, "get_context"):
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
    # A controller may set e.g. ``context["status_code"] = 404`` for a missing record,
    # ``content_type`` for a non-HTML page (an RSS feed), ``cache_seconds`` to let
    # browsers and a CDN keep a page that is the same for every reader and
    # ``headers`` of its own (``X-Frame-Options: SAMEORIGIN`` for an embeddable form).
    status_code = context.get("status_code") or 200
    headers: dict[str, str] = dict(context.get("headers") or {})
    cache_seconds = int(context.get("cache_seconds") or 0)
    if cache_seconds > 0 and status_code == 200 and request.method in ("GET", "HEAD"):
        headers["Cache-Control"] = f"public, max-age={cache_seconds}"
    return HTMLResponse(
        content=html,
        status_code=status_code,
        headers=headers,
        media_type=context.get("content_type") or "text/html",
    )


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
    """The page at the request's path: www files, web view documents, then the
    registered page resolvers."""
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

    # 3. Paths an app resolves itself (CMS pages, redirects)
    for resolver in _page_resolvers:
        response = await resolver(request, session)
        if response is not None:
            return response

    return None


NOT_FOUND_TEMPLATE = "_404.html"


async def render_not_found(request: Request, session: Any) -> Response | None:
    """404 in the site's own layout: ``www/_404.html`` (+ optional ``_404.py``
    controller) of the app the path belongs to - the one mounted at
    ``/<app>/...``, else the primary web app. ``None`` when that app has none.
    """
    from grunt.apps.loader import primary_web_app

    first = request.url.path.strip("/").split("/", 1)[0]
    for app in (first, primary_web_app()):
        if not app or website_registry.get_env(app) is None:
            continue
        www_dir = next((p.www_dir for p in website_registry.pages if p.app == app), None)
        if www_dir is None or not (www_dir / NOT_FOUND_TEMPLATE).is_file():
            continue
        page = WebsitePage(www_dir / NOT_FOUND_TEMPLATE, www_dir, app, request.url.path)
        response = await render_page(page, request, session=session)
        if response.status_code == 200:
            response.status_code = 404
            if "cache-control" in response.headers:
                del response.headers["cache-control"]
        return response
    return None


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


# A sitemap.xml file may hold at most 50 000 URLs (sitemaps.org).
SITEMAP_LIMIT = 50_000

SitemapEntry = str | tuple[str, Any]  # path, or (path, last modified)
_sitemap_sources: list[Any] = []


def register_sitemap_source(fn: Any) -> None:
    """Add ``async fn() -> Iterable[SitemapEntry]`` - pages an app serves that
    the sitemap can't discover itself (dynamic ``www/{param}`` routes).

    Registered from hooks.py: ``website_sitemap = ["app.module.fn"]``. Called
    as the system user; paths are site-relative (``/news/slug``).
    """
    if fn not in _sitemap_sources:
        _sitemap_sources.append(fn)


def _lastmod(value: Any) -> str:
    if isinstance(value, str):
        return value[:10]
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else ""


async def sitemap_entries() -> list[SitemapEntry]:
    """Every listed page: www pages, web view documents and every app's
    ``website_sitemap`` source (caller holds a grunt context)."""
    from grunt.website.generator import sitemap_urls

    entries: list[SitemapEntry] = [p.url_pattern for p in website_registry.pages if p.in_sitemap]
    entries.extend(await sitemap_urls())
    for source in _sitemap_sources:
        try:
            entries.extend(await source())
        except Exception as e:  # noqa: BLE001 - one app's bug must not drop the sitemap
            log.warning("website.sitemap.source_failed", source=repr(source), error=str(e))
    return entries


def render_sitemap(base: str, entries: list[SitemapEntry]) -> str:
    """sitemap.xml of *entries* (duplicates dropped, at most ``SITEMAP_LIMIT``)."""
    from xml.sax.saxutils import escape

    seen: set[str] = set()
    lines: list[str] = []
    for entry in entries:
        path, modified = entry if isinstance(entry, tuple) else (entry, None)
        if not path or path in seen:
            continue
        seen.add(path)
        lastmod = _lastmod(modified) if modified else ""
        lastmod_tag = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        lines.append(f"  <url><loc>{escape(base + path)}</loc>{lastmod_tag}</url>\n")
    if len(lines) > SITEMAP_LIMIT:
        log.warning("website.sitemap.truncated", total=len(lines), limit=SITEMAP_LIMIT)
        lines = lines[:SITEMAP_LIMIT]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{''.join(lines)}"
        "</urlset>"
    )


async def sitemap_xml(request: Request) -> Response:
    """Generate /sitemap.xml (see :func:`sitemap_entries`)."""
    import grunt
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.site.manager import site_manager

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.context(session, user=SYSTEM_USER):
        entries = await sitemap_entries()
    body = render_sitemap(str(request.base_url).rstrip("/"), entries)
    return Response(content=body, media_type="application/xml")


async def robots_txt(request: Request) -> PlainTextResponse:
    """Generate /robots.txt pointing crawlers at the sitemap."""
    base = str(request.base_url).rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /app/\nSitemap: {base}/sitemap.xml\n"
    return PlainTextResponse(content=body)
