from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from grunt.site.manager import current_site, site_manager

if TYPE_CHECKING:
    from fastapi import Request

logger = structlog.get_logger()


async def _apply_hot_reload_if_triggered(site: str) -> None:
    """Refresh this worker's in-memory DocType caches for *site* if
    `.reload_meta` is present (written by `grunt db migrate` / `grunt doctype
    sync`).

    Clearing the DocType cache is enough on its own: the next lazy-load
    re-reads the DocType's *stored* JSON blob (grunt_meta_doctype), which is
    the single source of truth for `permissions` too (edited in the Studio
    DocType builder, persisted in that blob).
    """
    reload_file = site_manager.sites_dir / site / ".reload_meta"
    if not reload_file.exists():
        return

    from grunt.metadata.registry import doctype_registry
    from grunt.scripting.file_scripts import FILE_CLIENT_SCRIPT_REGISTRY, _client_script_scanned

    doctype_registry.clear_cache()
    FILE_CLIENT_SCRIPT_REGISTRY.clear()
    _client_script_scanned.clear()

    try:
        reload_file.unlink()
    except Exception:
        logger.exception("suppressed_error")


class SiteContextMiddleware(BaseHTTPMiddleware):
    """Middleware to determine the active site based on request headers."""

    async def dispatch(self, request: Request, call_next):
        # 1. Check for explicit X-Grunt-Site header
        site = request.headers.get("x-grunt-site")

        # 2. Fallback to Host header (only if it matches a known site)
        if not site:
            host_header = request.headers.get("host", "")
            host_name = host_header.split(":")[0] if host_header else ""
            known_sites = site_manager.get_sites()
            if host_name in known_sites:
                site = host_name

        # 3. Hot reload: check for .reload_meta trigger (written by `grunt migrate`)
        if site:
            await _apply_hot_reload_if_triggered(site)

        # 3b. Fallback to currentsite.txt when Host header didn't match any site.
        if not site:
            try:
                fallback = site_manager.get_active_site()
                # Set the site so the context var is populated for downstream deps.
                site = fallback
                await _apply_hot_reload_if_triggered(fallback)
            except Exception:
                logger.warning("site.fallback_resolve_failed", host=host_header)

        # 4. Set site context var (or leave unset if still unknown).
        token = current_site.set(site) if site else None

        try:
            response = await call_next(request)
            return response
        finally:
            if token:
                current_site.reset(token)
