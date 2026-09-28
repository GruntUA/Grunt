"""Live introspection of the Redis Stream queue backing TaskIQ.

Powers the ``BackgroundJob``/``BackgroundWorker`` virtual DocTypes — the
analogue of Frappe's "RQ Job"/"RQ Worker": computed live from Redis on every
request, nothing persisted to SQL. Returns empty results when the broker
isn't Redis-backed (local dev's ``InMemoryBroker``) or Redis is unreachable —
these are monitoring views, never a hard dependency.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from grunt.i18n import N_, _
from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis.asyncio import Redis
    from taskiq_redis import RedisStreamBroker


def stream_broker() -> RedisStreamBroker | None:
    """The active broker, if it's Redis Stream-backed — ``None`` for InMemoryBroker."""
    from taskiq_redis import RedisStreamBroker

    from grunt.tasks.broker import broker

    return broker if isinstance(broker, RedisStreamBroker) else None


@asynccontextmanager
async def redis_conn() -> AsyncIterator[Redis | None]:
    """A connection borrowed from the broker's own pool, or ``None`` if unavailable."""
    sb = stream_broker()
    if sb is None:
        yield None
        return

    from redis.asyncio import Redis as AsyncRedis

    async with AsyncRedis(connection_pool=sb.connection_pool) as conn:
        yield conn


def s(value: Any) -> Any:
    """Decode a bytes value from a non-``decode_responses`` client; pass through others."""
    return value.decode() if isinstance(value, bytes) else value


def decode_message(raw: bytes) -> dict[str, Any]:
    """Best-effort decode of a stream entry's ``data`` field into task info."""
    sb = stream_broker()
    if sb is None:
        return {}
    try:
        message = sb.formatter.loads(raw)
    except Exception as exc:
        log.debug("redis_introspect.decode_failed", error=str(exc))
        return {}
    return {
        "task_id": message.task_id,
        "task_name": message.task_name,
        "args": message.args,
        "kwargs": message.kwargs,
        "labels": message.labels,
    }


def entry_timestamp_ms(message_id: str) -> int | None:
    """Redis stream ids are ``<ms-timestamp>-<seq>``."""
    try:
        return int(message_id.split("-", 1)[0])
    except ValueError, IndexError:
        return None


_UNAVAILABLE_MESSAGES = {
    "not_configured": N_("Redis is not configured: REDIS_URL is not set, live monitoring is off."),
    "unreachable": N_("Redis is unreachable; check that it is running."),
}


def unavailable_message(reason: str) -> str:
    """Human-readable text for a ``_load_all()`` failure reason.

    Redis-specific by design — callers (the BackgroundJob/BackgroundWorker
    controllers) put this straight in API ``meta`` for the frontend to
    display as-is, so no generic UI component ever needs to know Redis
    exists.
    """
    message = _UNAVAILABLE_MESSAGES.get(reason)
    return _(message) if message else _("The data source is temporarily unavailable.")
