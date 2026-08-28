"""Runtime access to the ``SystemSettings`` singleton.

Most of the framework needs to read one or two settings values on hot paths
(every login, every outgoing email, every push notification). Hitting the DB
each time is wasteful, so this module keeps a short-lived in-process cache of
the whole settings row.

The cache is invalidated two ways:

* explicitly — the ``SystemSettings`` controller calls :func:`clear_settings_cache`
  from ``after_save`` (see ``grunt/site/doctypes/SystemSettings/SystemSettings.py``);
* by TTL — a 60s backstop so that a settings change made in another worker
  process (production runs several) is picked up without a restart.

All accessors expect an active grunt context with a session (the callers —
auth, email, webpush — all run inside one).
"""

from __future__ import annotations

import time
from typing import Any

_SINGLETON = "SystemSettings"
_TTL_SECONDS = 60.0

_cache: dict[str, Any] | None = None
_cache_ts: float = 0.0


async def get_system_settings(*, fresh: bool = False) -> dict[str, Any]:
    """Return the full ``SystemSettings`` row as a dict (cached).

    Returns an empty dict if the singleton row does not exist yet (e.g. very
    early in a fresh install, before ``seed_system_settings`` has run).
    """
    global _cache, _cache_ts

    if not fresh and _cache is not None and (time.monotonic() - _cache_ts) < _TTL_SECONDS:
        return _cache

    from grunt.app import grunt

    # A singleton has exactly one row; read it positionally rather than by name
    # (the row may be autonamed to a hash on some sites).
    rows = await grunt.db.get_all(_SINGLETON, fields=None, limit=1)
    _cache = rows[0] if rows else {}
    _cache_ts = time.monotonic()
    return _cache


async def get_setting(field: str, default: Any = None) -> Any:
    """Return a single settings value, or *default* if unset.

    ``None`` (column NULL / missing) falls back to *default*; ``0``, ``False``
    and ``""`` are returned as-is — they are legitimate stored values.
    """
    settings = await get_system_settings()
    value = settings.get(field)
    return default if value is None else value


def clear_settings_cache() -> None:
    """Drop the cached settings row so the next read hits the DB."""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0
