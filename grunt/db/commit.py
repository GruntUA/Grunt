"""Work that must wait for the transaction to commit - ``on_commit``.

A side effect that tells someone else about a change (another process's
cache, a background worker, a browser, a remote server) has to wait until
the change is committed: told any earlier, they read the old row - or a row
that a rollback then takes back. ``on_commit(fn)`` runs *fn* once the
session's transaction commits and drops it on a rollback; outside a
transaction it runs at once. *fn* runs on the event loop after the commit
returns, best-effort: an error is logged, never raised into the request.

The queue lives in the session, in memory: a process that dies between the
commit and the call loses it. What must not be lost goes to the outbox.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.log import log
lazy from grunt.local import _session_ctx

_QUEUE = "grunt_on_commit"
_KEYS = "grunt_on_commit_keys"

_pending: set[asyncio.Task[None]] = set()


def on_commit(
    fn: Callable[[], Awaitable[Any]],
    *,
    session: AsyncSession | None = None,
    key: str | None = None,
) -> None:
    """Run *fn* once the transaction of *session* (the current one by default)
    commits; a rollback drops it; without a transaction - now.

    *key* - one call per key and transaction (repeated ``queue_email`` calls
    share a single queue kick).
    """
    session = session if session is not None else _session_ctx.get()
    if not isinstance(session, AsyncSession) or not session.in_transaction():
        _spawn(fn)
        return
    sync = session.sync_session
    queue = sync.info.get(_QUEUE)
    if queue is None:
        queue = sync.info[_QUEUE] = []
        sync.info[_KEYS] = set()
        event.listen(sync, "after_commit", _run_queued)
        event.listen(sync, "after_soft_rollback", _drop_queued)
    if key is not None:
        if key in sync.info[_KEYS]:
            return
        sync.info[_KEYS].add(key)
    queue.append(fn)


def _run_queued(sync: Any) -> None:
    queued = sync.info.get(_QUEUE) or []
    sync.info[_QUEUE], sync.info[_KEYS] = [], set()
    for fn in queued:
        _spawn(fn)


def _drop_queued(sync: Any, previous_transaction: Any) -> None:
    # The outer transaction only: a savepoint rollback keeps the rest of it.
    if previous_transaction.parent is None:
        sync.info[_QUEUE], sync.info[_KEYS] = [], set()


def _spawn(fn: Callable[[], Awaitable[Any]]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            await fn()
        except Exception:
            log.exception("db.on_commit_failed", fn=getattr(fn, "__qualname__", repr(fn)))

    task = loop.create_task(_run())
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain() -> None:
    """Wait for the work already started after a commit (shutdown, tests)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


__all__ = ["drain", "on_commit"]
