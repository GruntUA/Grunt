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
* on exit ``task_done`` is sent - ``error`` with the message if the block
  raised (the exception propagates), and with *doctype* the open list of that
  DocType refreshes;
* with ``cancellable=True`` the panel offers a cancel button
  (:func:`cancel_task`): the next :meth:`Progress.set`/:meth:`Progress.advance`
  raises :class:`TaskCancelledError` - the work's own error handling cleans up -
  and ``track_progress`` swallows it, reporting ``cancelled``.

Inside a background task (:data:`current_job` is set by
``grunt.tasks.middleware.TaskProgressMiddleware``) the state is also kept under
the task's id, user or not - so the «Active Background Tasks» list
(``BackgroundJob``) shows the progress of a scheduled run too, and a System
Manager can cancel it there (:func:`cancel_job`). Outside a task and without a
*user* nothing is published; the calls are no-ops.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Literal

import grunt
from grunt import log, whitelist
from grunt.api.v1.ws import manager
from grunt.config import settings
from grunt.utils.redis import connect

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

FLUSH_SECONDS = 0.5
_TTL_SECONDS = 24 * 3600  # a crashed worker's entry fades away by itself

Unit = Literal["bytes"] | None

# The taskiq id of the background task running in this context (None outside one).
current_job: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "grunt_progress_job", default=None
)


def _key(user: str, task_id: str = "*") -> str:
    return f"grunt:progress:{user}:{task_id}"


def _job_key(job_id: str) -> str:
    return f"grunt:progress-job:{job_id}"


def _cancel_key(task_id: str) -> str:
    return f"grunt:progress-cancel:{task_id}"


class TaskCancelledError(Exception):
    """Raised inside a tracked task once its user pressed cancel."""


async def _redis():
    if not settings.redis_url:
        return None

    return connect(socket_connect_timeout=1)


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
        cancellable: bool = False,
    ):
        self.task_id = uuid.uuid4().hex
        self.title = title
        self.user = user
        self.total = total
        self.done = 0
        self.stage: str | None = None
        self.step = 0  # «step N of M» when the work has distinct parts
        self.steps = 0
        self.unit = unit
        self.doctype = doctype
        self.started_at = time.time()
        self.cancellable = cancellable
        self.cancelled = False  # set by the flusher when the user asked to cancel
        self._version = 0  # bumped on every change; the flusher publishes when it moved

    def set(
        self,
        *,
        done: int | None = None,
        total: int | None = None,
        stage: str | None = None,
        step: int | None = None,
        steps: int | None = None,
    ):
        if step is not None:
            self.step = step
        if steps is not None:
            self.steps = steps
        if done is not None:
            self.done = done
        if total is not None:
            self.total = total
        if stage is not None:
            self.stage = stage
        self._version += 1
        self._check()

    def advance(self, n: int) -> None:
        self.done += n
        self._version += 1
        self._check()

    def _check(self) -> None:
        if self.cancelled:
            raise TaskCancelledError(self.title)

    def payload(self) -> dict[str, Any]:
        total = max(self.total, 0)
        return {
            "task_id": self.task_id,
            "title": self.title,
            "count": min(self.done, total) if total else self.done,
            "total": total,
            "percent": min(round(self.done * 100 / total), 99) if total else 0,
            "description": self.stage,
            "step": self.step,
            "steps": self.steps,
            "unit": self.unit,
            "started_at": self.started_at,
            "cancellable": self.cancellable,
        }


async def _send(user: str, event: str, data: dict[str, Any]) -> None:
    try:
        await manager.send_to_user(user, {"event": event, "data": data})
    except Exception:
        log.debug("progress.ws_send_failed", user=user, ws_event=event)


def _state_keys(p: Progress, job: str | None) -> list[str]:
    return ([_key(p.user, p.task_id)] if p.user else []) + ([_job_key(job)] if job else [])


async def _flush_loop(p: Progress, job: str | None, redis) -> None:
    sent = -1
    while True:
        if p._version != sent:
            sent = p._version
            data = p.payload()
            if p.user:
                await _send(p.user, "task_progress", data)
            if redis is not None:
                for key in _state_keys(p, job):
                    with contextlib.suppress(Exception):
                        await redis.set(key, json.dumps(data), ex=_TTL_SECONDS)
        if p.cancellable and redis is not None and not p.cancelled:
            with contextlib.suppress(Exception):
                p.cancelled = bool(await redis.exists(_cancel_key(p.task_id)))
        await asyncio.sleep(FLUSH_SECONDS)


@asynccontextmanager
async def track_progress(
    title: str,
    *,
    user: str | None,
    total: int = 0,
    unit: Unit = None,
    doctype: str | None = None,
    cancellable: bool = False,
) -> AsyncIterator[Progress]:
    """Report the progress of the enclosed work to *user* (see the module docstring)."""
    p = Progress(title, user=user, total=total, unit=unit, doctype=doctype)
    job = current_job.get()
    if not user and not job:
        yield p
        return

    redis = None
    with contextlib.suppress(Exception):
        redis = await _redis()
    # Cancelling goes through Redis (the button is pressed in the web process).
    p.cancellable = cancellable and redis is not None
    flusher = asyncio.create_task(_flush_loop(p, job, redis))
    status, message = "done", None
    try:
        yield p
    except TaskCancelledError:
        status = "cancelled"
    except BaseException as exc:
        status, message = "error", str(exc) or type(exc).__name__
        raise
    finally:
        flusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await flusher
        if redis is not None:
            with contextlib.suppress(Exception):
                await redis.delete(*_state_keys(p, job), _cancel_key(p.task_id))
                await redis.aclose()
        if user:
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
    """The current user's running tasks - the task panel restores itself from this."""
    redis = await _redis()
    if redis is None:
        return []
    tasks = []
    try:
        async for key in redis.scan_iter(match=_key(grunt.get_user().email)):
            with contextlib.suppress(Exception):
                if raw := await redis.get(key):
                    tasks.append(json.loads(raw))
    finally:
        await redis.aclose()
    return sorted(tasks, key=lambda t: t.get("started_at", 0))


@whitelist()
async def cancel_task(task_id: str) -> bool:
    """Ask the current user's running *task_id* to stop; False if there is no such task."""
    redis = await _redis()
    if redis is None:
        return False
    try:
        if not await redis.exists(_key(grunt.get_user().email, task_id)):
            return False
        await redis.set(_cancel_key(task_id), 1, ex=_TTL_SECONDS)
        return True
    finally:
        await redis.aclose()


async def job_progress(job_ids: list[str]) -> dict[str, dict[str, Any]]:
    """The tracked progress of the given background tasks (taskiq ids), by id."""
    if not job_ids:
        return {}
    redis = None
    with contextlib.suppress(Exception):
        redis = await _redis()
    if redis is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        raws = await redis.mget([_job_key(j) for j in job_ids])
        for job_id, raw in zip(job_ids, raws, strict=True):
            with contextlib.suppress(Exception):
                if raw:
                    out[job_id] = json.loads(raw)
    except Exception:
        log.debug("progress.job_progress_failed", exc_info=True)
    finally:
        await redis.aclose()
    return out


@whitelist(roles=["System Manager"])
async def cancel_job(job_id: str) -> bool:
    """Ask the background task *job_id* (any user's, or a scheduled one) to stop."""
    redis = await _redis()
    if redis is None:
        return False
    try:
        raw = await redis.get(_job_key(job_id))
        if not raw:
            return False
        data = json.loads(raw)
        if not data.get("cancellable"):
            return False
        await redis.set(_cancel_key(data["task_id"]), 1, ex=_TTL_SECONDS)
        return True
    finally:
        await redis.aclose()
