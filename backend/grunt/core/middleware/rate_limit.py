"""Rate limiting via slowapi (optional dependency)."""

from __future__ import annotations

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    _AVAILABLE = True
except ImportError:
    limiter = None  # type: ignore[assignment]
    _AVAILABLE = False


def is_available() -> bool:
    return _AVAILABLE
