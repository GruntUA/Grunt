from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from grunt import log
from grunt.db.write_intent import READ_ONLY_METHODS, set_write_intent
from grunt.metadata.compiler import clear_table_cache
from grunt.metadata.registry import get_registry
from grunt.scripting.file_scripts import FILE_CLIENT_SCRIPT_REGISTRY, _client_script_scanned
from grunt.site.manager import current_site, site_manager

if TYPE_CHECKING:
    from fastapi import Request


async def _apply_hot_reload_if_triggered(site: str) -> None:
    """Refresh *this site's* in-memory DocType cache if `.reload_meta` is
    present (written by `grunt db migrate` / `grunt doctype sync`).

    Clearing the DocType cache makes the next lazy-load re-read the DocType's
    *stored* JSON blob (grunt_meta_doctype), which is the single source of
    truth for `permissions` too (edited in the Studio DocType builder,
    persisted in that blob); the compiled Tables go too, or queries would
    keep the columns of before the migration.

    Scoped explicitly to *site* (via ``get_registry(site)``) rather than the
    ambient ``current_site`` ContextVar: one process can serve several
    sites, and migrating site A must never evict site B's warm cache too.
    """
    reload_file = site_manager.sites_dir / site / ".reload_meta"
    if not reload_file.exists():
        return

    get_registry(site).clear_cache()
    clear_table_cache(site)  # Tables compiled from the old definitions
    FILE_CLIENT_SCRIPT_REGISTRY.clear()
    _client_script_scanned.clear()

    try:
        reload_file.unlink()
    except Exception:
        log.exception("suppressed_error")


class SiteContextMiddleware(BaseHTTPMiddleware):
    """Middleware to determine the active site based on request headers."""

    async def dispatch(self, request: Request, call_next):
        # 1. Check for explicit X-Grunt-Site header
        site = request.headers.get("x-grunt-site")

        # 2. Fallback to Host header (only if it matches a known site)
        if not site:
            host_header = request.headers.get("host", "")
            host_name = host_header.split(":")[0] if host_header else ""
            if host_name in site_manager.get_sites():
                site = host_name

        # 3. Fallback to currentsite.txt when neither header matched a known site.
        if not site:
            try:
                site = site_manager.get_active_site()
            except Exception:
                log.warning("site.fallback_resolve_failed", host=request.headers.get("host", ""))

        # 4. Set the site context var BEFORE anything below resolves a
        # per-site resource (e.g. the DocType registry) off it.
        token = current_site.set(site) if site else None
        # SQLite: writing requests take the write lock at BEGIN (grunt/db/write_intent.py).
        set_write_intent(request.method not in READ_ONLY_METHODS)

        try:
            # 5. Hot reload: check for .reload_meta trigger (written by `grunt migrate`)
            if site:
                await _apply_hot_reload_if_triggered(site)

            response = await call_next(request)
            return response
        finally:
            if token:
                current_site.reset(token)
