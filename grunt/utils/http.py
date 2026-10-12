"""HTTP request helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from grunt.config import settings

if TYPE_CHECKING:
    from fastapi import Request


def _is_trusted_host(host: str | None) -> bool:
    """True when *host* is one this deployment actually serves.

    ``Origin`` and ``Host`` are set by the client - a script can send any value.
    A host is believed only if it names a configured site (site directories are
    named after their host), the ``APP_URL`` host or a CORS-allowed origin.
    """
    name = (host or "").split(":")[0].strip().lower()
    if not name:
        return False
    try:
        from grunt.site.manager import site_manager

        if name in site_manager.get_sites():
            return True
    except Exception:
        pass
    known = [settings.app_url, *settings.allowed_origins]
    return any((urlparse(o).hostname or "").lower() == name for o in known)


def public_base_url(request: Request | None) -> str:
    """The public origin the browser is actually on - ``scheme://host``.

    Reads ``Origin`` / ``Host`` + ``X-Forwarded-Proto`` so links built for
    emails and redirects resolve to the real domain behind a reverse proxy,
    not the ``APP_URL`` default - but only for a host this deployment serves
    (:func:`_is_trusted_host`). Anything else falls back to ``settings.app_url``:
    otherwise a forged header would put a real reset / sign-in token into a
    link on the attacker's domain (link poisoning -> account takeover).
    """
    fallback = settings.app_url.rstrip("/")
    if request is None:
        return fallback

    headers = request.headers
    origin = headers.get("origin")
    if origin and _is_trusted_host(urlparse(origin).hostname):
        return origin.rstrip("/")
    host = headers.get("host")
    if host and _is_trusted_host(host):
        proto = (headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        scheme = proto if proto in ("http", "https") else request.url.scheme
        return f"{scheme}://{host}"
    return fallback
