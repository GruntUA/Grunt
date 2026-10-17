"""Per-user/per-role rate limiting middleware.

Tiers (configurable via settings):
  System Manager - unlimited
  authenticated user - settings.rate_limit_user  (default 200 req/min)
  anonymous (IP) - settings.rate_limit_anon  (default 30 req/min)
  anonymous website page views (IP) - settings.rate_limit_pages  (default 300 req/min)
  public form submissions (IP) - settings.rate_limit_forms  (default 10 req/min)

Algorithm: fixed-window per 60-second bucket.
Storage:   in-memory dict (no Redis dependency; use Redis for multi-process).

JWT is decoded lightly - only to extract email + roles claims.
The signature IS verified (same secret_key) so the tier cannot be spoofed.
"""

import asyncio
import time
from collections import defaultdict
from html import escape
from typing import Any

import jwt
from fastapi import status
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from grunt import _, log
from grunt.auth.doctypes.UserSession.user_session import client_ip
from grunt.config import settings
from grunt.errors import error_body

# Paths that are always exempt from rate limiting (public assets, health checks)
_EXEMPT_PREFIXES = ("/assets/", "/api/docs", "/api/redoc", "/openapi.json", "/health")

# Strict per-IP overrides for sensitive auth endpoints (limit/minute).
# These apply before the standard per-user/per-tier logic.
_AUTH_STRICT_PATHS: dict[str, int] = {
    "/api/v1/method/grunt.auth.doctypes.User.user.login_api": 20,
    "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api": 10,
    "/api/v1/method/grunt.auth.doctypes.User.user.forgot_password_api": 5,
    "/api/v1/method/grunt.auth.doctypes.User.user.reset_password_api": 10,
    # Second factor / one-time codes: short and guessable, keep them slow.
    "/api/v1/method/grunt.auth.doctypes.User.user.mfa_login_api": 10,
    "/api/v1/method/grunt.auth.doctypes.User.user.mfa_enroll_complete": 10,
    "/api/v1/method/grunt.auth.doctypes.User.user.register": 10,
}

# /api/v1/auth/{method}/begin|complete|enroll/* - per-IP limit/minute.
_AUTH_METHODS_PREFIX = "/api/v1/auth/"
_AUTH_METHODS_LIMIT = 20

_FILE_CONTENT_PATH = "/api/v1/method/grunt.storage.doctypes.File.file.get_content"


def _is_file_content_request(request: Request) -> bool:
    """File downloads (signed private files and public ones alike).

    Public website images carry no signature, and an unsigned request for a
    private file is refused by get_content anyway - so the bucket keys on the
    path; guessing random file ids at this rate is not a practical attack.
    """
    return request.url.path == _FILE_CONTENT_PATH


def _is_page_view(path: str, method: str) -> bool:
    """A website page (or the SPA shell) - not the API.

    Readers behind one address (an office NAT, a mobile carrier's CGNAT) share
    the bucket, so it is far wider than the API's anonymous one.
    """
    return method in ("GET", "HEAD") and not path.startswith("/api/")


def _too_many_requests(path: str, reset_in: int, headers: dict[str, str]) -> Response:
    """429 as JSON for the API, as a plain page for a browser on the website."""
    message = _("Too many requests. Try again later.")
    headers = {"Retry-After": str(reset_in), **headers}
    if path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_body("RATE_LIMIT_EXCEEDED", message),
            headers=headers,
        )
    body = f'<!DOCTYPE html><meta charset="utf-8"><title>429</title><p>{escape(message)}</p>'
    return HTMLResponse(body, status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers=headers)


def _is_form_submit(path: str, method: str) -> bool:
    """A POST to a website page - a public form (CMS web form, an app's own
    form). Open to anonymous traffic by design, so it gets its own tighter
    bucket rather than the general anonymous one."""
    return method == "POST" and not path.startswith("/api/")


class _Window:
    """Single fixed-window counter for one key."""

    __slots__ = ("count", "reset_at")

    def __init__(self, reset_at: float) -> None:
        self.count = 0
        self.reset_at = reset_at


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-user / per-IP rate limiting with three tiers.

    Configuration via settings:
        rate_limit_user - max requests per minute for authenticated users
        rate_limit_anon - max requests per minute for anonymous (IP-based) API calls
        rate_limit_pages - the same for anonymous website page views
        rate_limit_enabled - set False to disable entirely
    """

    def __init__(self, app: Any, window_seconds: int = 60) -> None:
        super().__init__(app)
        self._window = window_seconds
        # {key: _Window}
        self._counters: dict[str, _Window] = defaultdict(lambda: _Window(0.0))
        self._lock = asyncio.Lock()

    # Core logic

    def _decode_token(self, authorization: str | None) -> dict | None:
        """Decode JWT bearer token and return payload, or None on any failure."""
        if not authorization or not authorization.startswith("Bearer "):
            return None
        token = authorization[7:]
        try:
            return jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
                options={"verify_exp": False},  # expiry enforced by auth layer
            )
        except jwt.PyJWTError:
            return None

    async def _check(self, key: str, limit: int) -> tuple[bool, int, int]:
        """Check and increment counter.

        Returns:
            (allowed, remaining, reset_in_seconds)
        """
        now = time.monotonic()
        async with self._lock:
            win = self._counters[key]
            if now >= win.reset_at:
                win.count = 0
                win.reset_at = now + self._window
            win.count += 1
            allowed = win.count <= limit
            remaining = max(0, limit - win.count)
            reset_in = max(0, int(win.reset_at - now))
        return allowed, remaining, reset_in

    def _client_ip(self, request: Request) -> str:
        return client_ip(request) or "unknown"

    async def _cleanup(self) -> None:
        """Evict stale windows (called periodically; best-effort)."""
        now = time.monotonic()
        async with self._lock:
            stale = [k for k, w in self._counters.items() if now > w.reset_at + self._window]
            for k in stale:
                del self._counters[k]

    # Middleware dispatch

    async def dispatch(self, request: Request, call_next) -> Response:
        # Feature flag
        if not getattr(settings, "rate_limit_enabled", True):
            return await call_next(request)

        # Exempt paths
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Strict IP-based limits for sensitive auth paths (regardless of user tier)
        strict_limit = _AUTH_STRICT_PATHS.get(path)
        if (
            strict_limit is None
            and request.method == "POST"
            and path.startswith(_AUTH_METHODS_PREFIX)
        ):
            # Pluggable sign-in methods (email code, passkey, ...): one bucket each.
            strict_limit = _AUTH_METHODS_LIMIT
        if strict_limit is not None:
            ip = self._client_ip(request)
            strict_key = f"auth:{path}:{ip}"
            allowed, remaining, reset_in = await self._check(strict_key, strict_limit)
            if not allowed:
                log.warning("rate_limit.auth_exceeded", path=path, ip=ip)
                return _too_many_requests(path, reset_in, {})

        # Strict IP-based limit for public form submissions
        if _is_form_submit(path, request.method):
            form_limit = getattr(settings, "rate_limit_forms", 10)
            ip = self._client_ip(request)
            form_key = f"form:{path}:{ip}"
            allowed, remaining, reset_in = await self._check(form_key, form_limit)
            if not allowed:
                log.warning("rate_limit.form_exceeded", path=path, ip=ip)
                return _too_many_requests(path, reset_in, {})

        # Decode JWT (optional - does not affect auth, only rate limit tier)
        payload = self._decode_token(request.headers.get("authorization"))

        if not payload and _is_file_content_request(request):
            # <img> / links carry no Authorization header: a grid of previews
            # (or a public page's pictures) would drain the anonymous budget in
            # one page view. File downloads get their own, more generous bucket.
            limit = getattr(settings, "rate_limit_files", 600)
            key = f"files:{self._client_ip(request)}"
        elif payload:
            is_system_manager = "System Manager" in (payload.get("roles") or [])
            email: str = payload.get("sub") or payload.get("email") or "unknown"

            # System Manager: unlimited
            if is_system_manager:
                return await call_next(request)

            limit: int = getattr(settings, "rate_limit_user", 200)
            key = f"user:{email}"
        elif _is_page_view(path, request.method):
            limit = getattr(settings, "rate_limit_pages", 300)
            key = f"pages:{self._client_ip(request)}"
        else:
            limit = getattr(settings, "rate_limit_anon", 30)
            key = f"ip:{self._client_ip(request)}"

        allowed, remaining, reset_in = await self._check(key, limit)

        if not allowed:
            log.warning(
                "rate_limit.exceeded",
                key=key,
                limit=limit,
                path=path,
            )
            return _too_many_requests(
                path,
                reset_in,
                {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_in),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
        return response
