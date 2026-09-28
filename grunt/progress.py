"""Progress of long tasks (backups, imports…) for the user who started them.

Usage in a background task::

    from grunt.progress import track_progress

    async with track_progress(_("Backup"), user=email, total=nbytes, unit="bytes") as p:
        p.set(stage=_("Archiving files"))
        p.advance(len(chunk))  # safe to call from a worker thread too

The frontend's floating task panel (``TaskProgressPanel.vue``) shows it:

* ``task_progress`` events go to the user's WebSocket at most every
  :data:`FLUSH_SECONDS`, so a tight loop can report every chunk;
* the state is kept in Redis while the task runs, so a page reload picks it up
  again (:func:`active_tasks`);
* on exit ``task_done`` is sent — ``error`` with the message if the block
  raised (the exception propagates), and with *doctype* the open list of that
  DocType refreshes.

Without a *user* (a scheduled run) nothing is published; the calls are no-ops.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Literal

from grunt import whitelist
from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

FLUSH_SECONDS = 0.5
_TTL_SECONDS = 24 * 3600  # a crashed worker's entry fades away by itself

Unit = Literal["bytes"] | None


def _key(user: str, task_id: str = "*") -> str:
    return f"grunt:progress:{user}:{task_id}"


async def _redis():
    from grunt.config import settings

    if not settings.redis_url:
        return None
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.redis_url, socket_connect_timeout=1)


class Progress:
    """Mutable progress of one task; :meth:`set`/:meth:`advance` never block."""

    def __init__(
        self,
        title: str,
        *,
        user: str | None,
        total: int = 0,
        unit: Unit = None,
        doctype: str | None = None,
    ):
        self.task_id = uuid.uuid4().hex
        self.title = title
        self.user = user
        self.total = total
        self.done = 0
        self.stage: str | None = None
        self.unit = unit
        self.doctype = doctype
        self.started_at = time.time()
        self._version = 0  # bumped on every change; the flusher publishes when it moved

    def set(self, *, done: int | None = None, total: int | None = None, stage: str | None = None):
        if done is not None:
            self.done = done
        if total is not None:
            self.total = total
        if stage is not None:
            self.stage = stage
        self._version += 1

    def advance(self, n: int) -> None:
        self.done += n
        self._version += 1

    def payload(self) -> dict[str, Any]:
        total = max(self.total, 0)
        return {
            "task_id": self.task_id,
            "title": self.title,
            "count": min(self.done, total) if total else self.done,
            "total": total,
            "percent": min(round(self.done * 100 / total), 99) if total else 0,
            "description": self.stage,
            "unit": self.unit,
            "started_at": self.started_at,
        }


async def _send(user: str, event: str, data: dict[str, Any]) -> None:
    from grunt.api.v1.ws import manager

    try:
        await manager.send_to_user(user, {"event": event, "data": data})
    except Exception:
        log.debug("progress.ws_send_failed", user=user, ws_event=event)


async def _flush_loop(p: Progress, redis) -> None:
    sent = -1
    while True:
        if p._version != sent:
            sent = p._version
            data = p.payload()
            await _send(p.user, "task_progress", data)  # type: ignore[arg-type]
            if redis is not None:
                with contextlib.suppress(Exception):
                    await redis.set(_key(p.user, p.task_id), json.dumps(data), ex=_TTL_SECONDS)
        await asyncio.sleep(FLUSH_SECONDS)


@asynccontextmanager
async def track_progress(
    title: str,
    *,
    user: str | None,
    total: int = 0,
    unit: Unit = None,
    doctype: str | None = None,
) -> AsyncIterator[Progress]:
    """Report the progress of the enclosed work to *user* (see the module docstring)."""
    p = Progress(title, user=user, total=total, unit=unit, doctype=doctype)
    if not user:
        yield p
        return

    redis = None
    with contextlib.suppress(Exception):
        redis = await _redis()
    flusher = asyncio.create_task(_flush_loop(p, redis))
    status, message = "done", None
    try:
        yield p
    except BaseException as exc:
        status, message = "error", str(exc) or type(exc).__name__
        raise
    finally:
        flusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await flusher
        if redis is not None:
            with contextlib.suppress(Exception):
                await redis.delete(_key(user, p.task_id))
                await redis.aclose()
        await _send(
            user,
            "task_done",
            {
                "task_id": p.task_id,
                "title": title,
                "status": status,
                "message": message,
                "doctype": doctype,
            },
        )


@whitelist()
async def active_tasks() -> list[dict[str, Any]]:
    """The current user's running tasks — the task panel restores itself from this."""
    from grunt.app import grunt

    redis = await _redis()
    if redis is None:
        return []
    tasks = []
    try:
        async for key in redis.scan_iter(match=_key(grunt.session.user)):
            with contextlib.suppress(Exception):
                if raw := await redis.get(key):
                    tasks.append(json.loads(raw))
    finally:
        await redis.aclose()
    return sorted(tasks, key=lambda t: t.get("started_at", 0))
