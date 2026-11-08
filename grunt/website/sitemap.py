"""``/sitemap.xml`` and ``/robots.txt``: www pages, web view documents and
every app's ``website_sitemap`` source - the pages of the host asked
(see ``web_domains``)."""

from collections.abc import Callable
from typing import Any
lazy from xml.sax.saxutils import escape

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response

import grunt
from grunt import log
from grunt.website.host import current_web_app
lazy from grunt.auth.doctypes.User.user import SYSTEM_USER
lazy from grunt.site.manager import site_manager
lazy from grunt.website.generator import sitemap_urls
lazy from grunt.website.router import website_registry

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


def _sitemap_scope() -> Callable[[str | None], bool]:
    """Which apps' pages this host's sitemap lists: on an app's own domain that
    app only; elsewhere every app but those with a domain of their own."""
    web_app = current_web_app.get()
    if web_app:
        return lambda app: app == web_app
    elsewhere = set(site_manager.domain_apps(site_manager.get_active_site()))
    return lambda app: app not in elsewhere


async def sitemap_entries() -> list[SitemapEntry]:
    """Every listed page of this host: www pages, web view documents and every
    app's ``website_sitemap`` source (caller holds a grunt context)."""

    include = _sitemap_scope()
    entries: list[SitemapEntry] = [
        p.url_pattern for p in website_registry.pages if p.in_sitemap and include(p.app)
    ]
    entries.extend(await sitemap_urls(include))
    for source in _sitemap_sources:
        if not include(getattr(source, "__module__", "").split(".")[0]):
            continue
        try:
            entries.extend(await source())
        except Exception as e:  # noqa: BLE001 - one app's bug must not drop the sitemap
            log.warning("website.sitemap.source_failed", source=repr(source), error=str(e))
    return entries


def render_sitemap(base: str, entries: list[SitemapEntry]) -> str:
    """sitemap.xml of *entries* (duplicates dropped, at most ``SITEMAP_LIMIT``)."""

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
