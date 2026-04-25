from __future__ import annotations

import structlog
logger = structlog.get_logger()
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from grunt.core.site.manager import current_site, site_manager
from grunt.config import settings

if TYPE_CHECKING:
    from fastapi import Request


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

        # 3. Development hot reload: check for .reload_meta trigger
        if site and settings.debug:
            reload_file = site_manager.sites_dir / site / ".reload_meta"
            if reload_file.exists():
                from grunt.core.metadata.registry import doctype_registry
                doctype_registry.clear_cache()
                try:
                    reload_file.unlink()
                except Exception:
                    logger.exception("suppressed_error")

        # 4. If still no site — don't set context, let get_active_site()
        #    fallback to currentsite.txt
        token = current_site.set(site) if site else None

        try:
            response = await call_next(request)
            return response
        finally:
            if token:
                current_site.reset(token)
