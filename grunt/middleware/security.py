"""Security headers middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

# A year; sent over HTTPS only (a plain-HTTP response can't pin anything).
HSTS = "max-age=31536000"

# What every page may safely forbid without knowing its scripts and styles:
# no plugins, no <base> hijacking, framing only as X-Frame-Options allows.
_CSP = "object-src 'none'; base-uri 'self'; frame-ancestors {}"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # Defaults only: an endpoint may set its own (e.g. X-Frame-Options:
        # SAMEORIGIN for a file previewed in an <iframe> on the site).
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        frame = headers.setdefault("X-Frame-Options", "DENY")
        ancestors = "'self'" if frame.upper() == "SAMEORIGIN" else "'none'"
        headers.setdefault("Content-Security-Policy", _CSP.format(ancestors))
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
        if request.url.scheme == "https":
            headers.setdefault("Strict-Transport-Security", HSTS)
        return response
