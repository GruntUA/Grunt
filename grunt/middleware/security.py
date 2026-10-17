"""Security headers middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
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
        # Behind a TLS-terminating proxy (the usual prod setup: nginx -> uvicorn)
        # the request reaches the app as plain HTTP, so request.url.scheme is
        # "http" and HSTS would never be sent. Trust X-Forwarded-Proto too - a
        # browser only honours HSTS received over real HTTPS, so emitting it on a
        # genuinely-HTTP response (were the header forged) is simply ignored.
        forwarded_proto = (
            (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        )
        if request.url.scheme == "https" or forwarded_proto == "https":
            headers.setdefault("Strict-Transport-Security", HSTS)
        return response
