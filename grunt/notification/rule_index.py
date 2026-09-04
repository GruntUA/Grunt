"""Which ``(doctype, event)`` pairs have at least one enabled ``NotificationRule``.

The hook bus (:func:`grunt.hooks.fire`, stage 5) consults this before it offloads
notification-rule evaluation to a background worker. Without the check *every*
document write in the system enqueues a worker task — and a ``BackgroundTaskLog``
row — even when no rule could ever match it.

Modelled on :mod:`grunt.workflow.registry`: a process-local snapshot kept fresh by
``NotificationRule`` change hooks (wired in ``grunt.main``), with a short TTL so
other worker/web processes pick up rule changes without a restart.
"""

from __future__ import annotations

import time

from grunt.log import log

# Upper bound on how long a process keeps serving a stale snapshot when the rule
# change happened in *another* process (the invalidation hook only fires in the
# one that handled the edit).
_TTL_SECONDS = 60.0

_pairs: frozenset[tuple[str, str]] | None = None
_loaded_at = 0.0


def invalidate() -> None:
    """Drop the cached snapshot; the next :func:`has_rules` call reloads it."""
    global _pairs
    _pairs = None


def invalidate_on_change(**_kwargs: object) -> None:
    """Doc-event hook target for ``NotificationRule`` after_save / after_delete."""
    invalidate()


async def _load() -> frozenset[tuple[str, str]] | None:
    """Read every enabled rule's ``(doctype, event)``; ``None`` if no session bound."""
    from sqlalchemy import select

    from grunt.context import _session_ctx
    from grunt.document.meta import Meta
    from grunt.metadata.registry import doctype_registry

    session = _session_ctx.get()
    if session is None:
        return None

    dt = await doctype_registry.get("NotificationRule")
    table = Meta(dt).table
    result = await session.execute(
        select(table.c.doctype, table.c.event).where(table.c.is_enabled.is_(True))
    )
    return frozenset((str(d), str(e)) for d, e in result.all() if d and e)


async def has_rules(doctype: str, event: str) -> bool:
    """True if an enabled ``NotificationRule`` targets this *doctype* + *event*.

    Fails open: if the snapshot cannot be loaded (no session bound, DB error) it
    returns ``True`` so the background worker still gets a chance to evaluate.
    """
    global _pairs, _loaded_at
    now = time.monotonic()
    if _pairs is None or now - _loaded_at > _TTL_SECONDS:
        try:
            loaded = await _load()
        except Exception:
            log.exception("notification.rule_index_load_failed")
            return True
        if loaded is None:
            return True
        _pairs = loaded
        _loaded_at = now
    return (doctype, event) in _pairs
