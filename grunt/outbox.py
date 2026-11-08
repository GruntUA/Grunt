"""The outbox - side effects that must not be lost, delivered after the commit.

A message to the outside world (a webhook POST) can't be sent inside the
transaction that makes the change: the request would wait on a remote server,
SQLite would hold its write lock all that time, and a rollback could not take
the message back. Sent after the commit from memory (:func:`on_commit`), it
is lost with the process.

``put(handler, payload)`` writes the message as a row of ``grunt_core_outbox``
in the same transaction as the change - both commit, or neither. After the
commit :func:`deliver` runs in a worker: it claims each due row, calls
``handler(payload)`` and deletes the row; a handler that raises is retried
later with a growing backoff, up to :data:`MAX_ATTEMPTS`. The scheduler runs
:func:`deliver` every minute too - for retries and for rows a crashed worker
left behind.

A handler is a module-level async function, stored by its dotted path. It
runs in a system context, and must commit before network I/O - an open
transaction would hold the database (SQLite: the write lock) while it waits.
"""

import importlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import log
from grunt.db.commit import on_commit
from grunt.metadata.compiler import OUTBOX_TABLE
from grunt.site.manager import site_manager
from grunt.tasks.broker import task

#: Attempts before a message is given up (logged as an error and dropped).
MAX_ATTEMPTS = 8
#: How long a delivery holds its row - after that another run may take it.
_CLAIM = timedelta(minutes=5)
#: Messages one run delivers at most (the next run - kick or tick - takes the rest).
_BATCH = 200

type Handler = Callable[[dict[str, Any]], Awaitable[Any]]


def _path(handler: Handler) -> str:
    path = f"{handler.__module__}.{handler.__qualname__}"
    if "<" in path:
        raise ValueError(f"outbox handler must be a module-level function, not {path}")
    return path


def _resolve(path: str) -> Handler:
    module, _sep, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


def backoff(attempts: int) -> timedelta:
    """The wait before attempt *attempts* + 1: 30 s, 1 min, 2 min … capped at 6 h."""
    exponent = min(max(attempts - 1, 0), 10)  # 30 s * 2**10 is past the cap already
    return min(timedelta(seconds=30 * 2**exponent), timedelta(hours=6))


async def put(
    handler: Handler, payload: dict[str, Any], *, session: AsyncSession | None = None
) -> None:
    """Write a message for *handler* in the current transaction; it is delivered
    once the transaction commits (a rollback drops it with the change)."""
    session = session if session is not None else grunt.get_session()
    now = datetime.now(UTC)
    await session.execute(
        OUTBOX_TABLE.insert().values(
            handler=_path(handler), payload=payload, attempts=0, due_at=now, created_at=now
        )
    )
    on_commit(_kick, session=session, key="outbox.kick")


async def _kick() -> None:
    await deliver.kiq()


async def _claim(session: AsyncSession, now: datetime) -> dict[str, Any] | None:
    """The next due message, claimed for this run (``None`` - nothing due)."""
    t = OUTBOX_TABLE
    free = or_(t.c.claimed_until.is_(None), t.c.claimed_until < now)
    while True:
        row = (
            await session.execute(
                select(t).where(t.c.due_at <= now, free).order_by(t.c.due_at, t.c.id).limit(1)
            )
        ).first()
        if row is None:
            return None
        claimed = await session.execute(
            update(t).where(t.c.id == row.id, free).values(claimed_until=now + _CLAIM)
        )
        await session.commit()
        if claimed.rowcount:  # type: ignore[attr-defined]
            return dict(row._mapping)
        # Another run took it between the SELECT and the UPDATE - next one.


async def _settle(session: AsyncSession, message: dict[str, Any], error: Exception | None) -> None:
    t = OUTBOX_TABLE
    if error is None:
        await session.execute(delete(t).where(t.c.id == message["id"]))
    else:
        attempts = message["attempts"] + 1
        if attempts >= MAX_ATTEMPTS:
            log.error(
                "outbox.given_up",
                handler=message["handler"],
                attempts=attempts,
                error=str(error),
            )
            await session.execute(delete(t).where(t.c.id == message["id"]))
        else:
            await session.execute(
                update(t)
                .where(t.c.id == message["id"])
                .values(
                    attempts=attempts,
                    due_at=datetime.now(UTC) + backoff(attempts),
                    claimed_until=None,
                    last_error=str(error)[:4000],
                )
            )
    await session.commit()


async def deliver_due(session: AsyncSession) -> int:
    """Deliver the messages due now in *session*; returns how many went out."""
    delivered = 0
    for _ in range(_BATCH):
        message = await _claim(session, datetime.now(UTC))
        if message is None:
            break
        error: Exception | None = None
        try:
            await _resolve(message["handler"])(message["payload"])
        except Exception as exc:  # noqa: BLE001 - a failed delivery is retried, not raised
            await session.rollback()
            error = exc
            log.warning("outbox.delivery_failed", handler=message["handler"], error=str(exc))
        await _settle(session, message, error)
        delivered += error is None
    return delivered


@task
async def deliver() -> int:
    """Deliver the site's due outbox messages - after a commit that wrote some,
    and every minute (retries, rows a crashed run left behind)."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    async with maker() as session, grunt.system_context(session, site_manager.get_engine(site)):
        return await deliver_due(session)


__all__ = ["MAX_ATTEMPTS", "backoff", "deliver", "deliver_due", "put"]
