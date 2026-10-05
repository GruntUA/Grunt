"""HTTP request helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.config import settings

if TYPE_CHECKING:
    from fastapi import Request


def public_base_url(request: Request | None) -> str:
    """The public origin the browser is actually on - ``scheme://host``.

    Reads ``Origin`` / ``Host`` + ``X-Forwarded-Proto`` so links built for
    emails and redirects resolve to the real domain behind a reverse proxy,
    not the ``APP_URL`` default. Falls back to ``settings.app_url`` when no
    usable headers are present (or there is no request at all).
    """
    fallback = settings.app_url.rstrip("/")
    if request is None:
        return fallback

    headers = request.headers
    origin = headers.get("origin")
    if origin:
        return origin.rstrip("/")
    host = headers.get("host")
    if host:
        scheme = headers.get("x-forwarded-proto") or request.url.scheme
        return f"{scheme}://{host}"
    return fallback
