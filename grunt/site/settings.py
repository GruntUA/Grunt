"""Runtime access to the ``SystemSettings`` singleton.

Most of the framework needs to read one or two settings values on hot paths
(every login, every outgoing email, every push notification). Hitting the DB
each time is wasteful, so this module keeps a short-lived in-process cache of
the whole settings row.

The cache is invalidated two ways:

* explicitly - the ``SystemSettings`` controller calls :func:`clear_settings_cache`
  from ``after_save`` (see ``grunt/site/doctypes/SystemSettings/SystemSettings.py``),
  which reaches the other worker processes through :mod:`grunt.cache.bus`;
* by TTL - a 60s backstop for a lost bus message (or no Redis).

The cache is per site: one process serves every site of the bench.

All accessors expect an active grunt context with a session (the callers -
auth, email, webpush - all run inside one).
"""

import time
from typing import Any

from sqlalchemy import select

from grunt.cache.bus import fanout
from grunt.local import require_session
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import current_site

_SINGLETON = "SystemSettings"
_TTL_SECONDS = 60.0

# site -> (loaded at, the settings row)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def get_system_settings(*, fresh: bool = False) -> dict[str, Any]:
    """Return the full ``SystemSettings`` row as a dict (cached).

    Returns an empty dict if the singleton row does not exist yet (e.g. very
    early in a fresh install, before ``seed_system_settings`` has run).
    """
    site = current_site.get()
    hit = _cache.get(site)
    if not fresh and hit is not None and (time.monotonic() - hit[0]) < _TTL_SECONDS:
        return hit[1]

    # A singleton has exactly one row; read it positionally rather than by name
    # (the row may be autonamed to a hash on some sites).
    # Straight from the table: the settings sit below queries and permissions
    # (which read them), so they can't go through grunt.db.
    meta = await doctype_registry.get_meta(_SINGLETON)
    found = None
    if meta is not None:
        result = await require_session().execute(select(meta.table).limit(1))
        found = result.mappings().first()
    row = dict(found) if found is not None else {}
    _cache[site] = (time.monotonic(), row)
    return row


async def get_setting(field: str, default: Any = None) -> Any:
    """Return a single settings value, or *default* if unset.

    ``None`` (column NULL / missing) falls back to *default*; ``0``, ``False``
    and ``""`` are returned as-is - they are legitimate stored values.
    """
    settings = await get_system_settings()
    value = settings.get(field)
    return default if value is None else value


@fanout
def clear_settings_cache() -> None:
    """Drop the cached settings rows so the next read hits the DB."""
    _cache.clear()
