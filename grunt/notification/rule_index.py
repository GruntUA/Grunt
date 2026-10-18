"""Which ``(doctype, event)`` pairs have at least one enabled ``NotificationRule``.

The hook bus (:func:`grunt.hooks.fire`, stage 5) consults this before it offloads
notification-rule evaluation to a background worker. Without the check *every*
document write in the system enqueues a worker task, even when no rule could
ever match it.

Modelled on :mod:`grunt.workflow.registry`: a process-local snapshot per site,
kept fresh by ``NotificationRule`` change hooks (wired in ``grunt.core_hooks``)
in every process via :mod:`grunt.cache.bus`, with a short TTL as the backstop.
"""

import time

from sqlalchemy import select

import grunt
from grunt import _, log
from grunt.cache.bus import fanout
from grunt.local import _session_ctx
from grunt.site.manager import current_site
lazy from grunt.errors import not_found

# Upper bound on how long a process keeps serving a stale snapshot when the
# invalidation from another process got lost.
_TTL_SECONDS = 60.0

# site -> (loaded at, enabled (doctype, event) pairs)
_snapshots: dict[str, tuple[float, frozenset[tuple[str, str]]]] = {}


@fanout
def invalidate() -> None:
    """Drop the site's cached snapshot; the next :func:`has_rules` call reloads it."""
    _snapshots.pop(current_site.get(), None)


def invalidate_on_change(**_kwargs: object) -> None:
    """Doc-event hook target for ``NotificationRule`` after_save / after_delete."""
    invalidate()


async def _load() -> frozenset[tuple[str, str]] | None:
    """Read every enabled rule's ``(doctype, event)``; ``None`` if no session bound."""

    session = _session_ctx.get()
    if session is None:
        return None

    dt = await grunt.get_meta("NotificationRule")
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "NotificationRule"})
    table = dt.table
    result = await session.execute(
        select(table.c.ref_doctype, table.c.event).where(table.c.is_enabled.is_(True))
    )
    return frozenset((str(d), str(e)) for d, e in result.all() if d and e)


async def has_rules(doctype: str, event: str) -> bool:
    """True if an enabled ``NotificationRule`` targets this *doctype* + *event*.

    Fails open: if the snapshot cannot be loaded (no session bound, DB error) it
    returns ``True`` so the background worker still gets a chance to evaluate.
    """
    site = current_site.get()
    now = time.monotonic()
    hit = _snapshots.get(site)
    if hit is None or now - hit[0] > _TTL_SECONDS:
        try:
            loaded = await _load()
        except Exception:
            log.exception("notification.rule_index_load_failed")
            return True
        if loaded is None:
            return True
        hit = _snapshots[site] = (now, loaded)
    return (doctype, event) in hit[1]
