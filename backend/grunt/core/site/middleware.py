from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from grunt.core.site.manager import current_site

class SiteContextMiddleware(BaseHTTPMiddleware):
    """Middleware to determine the active site based on request headers."""

    async def dispatch(self, request: Request, call_next):
        # 1. Check for explicit X-Grunt-Site header
        site = request.headers.get("x-grunt-site")
        
        # 2. Fallback to Host header
        if not site:
            host_header = request.headers.get("host", "")
            site = host_header.split(":")[0] if host_header else None
            
        # 3. If no site determinable, fallback to default logic in get_active_site()
        # but for safety, we try to set it if we got something
        if site:
            token = current_site.set(site)
        else:
            token = None
            
        try:
            response = await call_next(request)
            return response
        finally:
            if token:
                current_site.reset(token)
