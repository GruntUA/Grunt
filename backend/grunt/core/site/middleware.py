from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from grunt.core.site.manager import current_site, site_manager


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

        # 3. If still no site — don't set context, let get_active_site()
        #    fallback to currentsite.txt
        token = current_site.set(site) if site else None

        try:
            response = await call_next(request)
            return response
        finally:
            if token:
                current_site.reset(token)
