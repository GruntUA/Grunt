"""Live introspection of the Redis Stream queue backing TaskIQ.

Powers the ``BackgroundJob``/``BackgroundWorker`` virtual DocTypes - the
analogue of Frappe's "RQ Job"/"RQ Worker": computed live from Redis on every
request, nothing persisted to SQL. Returns empty results when the broker
isn't Redis-backed (local dev's ``InMemoryBroker``) or Redis is unreachable -
these are monitoring views, never a hard dependency.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from grunt import log
from grunt.i18n import N_, _
from grunt.tasks.broker import broker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis.asyncio import Redis
    from taskiq_redis import RedisStreamBroker


def stream_broker() -> RedisStreamBroker | None:
    """The active broker, if it's Redis Stream-backed - ``None`` for InMemoryBroker."""
    from taskiq_redis import RedisStreamBroker

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


# A live worker polls XREADGROUP every few seconds, which resets its ``idle``;
# past this it has stopped polling - crashed or restarted under a new name.
DEAD_CONSUMER_IDLE_MS = 10 * 60 * 1000


async def prune_dead_consumers(min_idle_ms: int = DEAD_CONSUMER_IDLE_MS) -> int:
    """Drop consumer-group members that stopped polling and own no pending messages.

    Every worker process registers under a fresh uuid, so each restart leaves
    the old name behind in ``XINFO CONSUMERS``. ``XGROUP DELCONSUMER`` discards
    the consumer's pending entries, so one that still holds any is kept until a
    live worker ``XAUTOCLAIM``s them. Returns the number removed.
    """
    sb = stream_broker()
    if sb is None:
        return 0
    removed = 0
    async with redis_conn() as conn:
        assert conn is not None
        for c in await conn.xinfo_consumers(sb.queue_name, sb.consumer_group_name):
            if int(c.get("pending", 0)) or int(c.get("idle", 0)) < min_idle_ms:
                continue
            await conn.xgroup_delconsumer(sb.queue_name, sb.consumer_group_name, s(c["name"]))
            removed += 1
    return removed


async def unregister_consumer() -> None:
    """Remove this process's own consumer on graceful shutdown, unless it holds pending work."""
    sb = stream_broker()
    if sb is None:
        return
    async with redis_conn() as conn:
        assert conn is not None
        for c in await conn.xinfo_consumers(sb.queue_name, sb.consumer_group_name):
            if s(c.get("name")) == sb.consumer_name and not int(c.get("pending", 0)):
                await conn.xgroup_delconsumer(
                    sb.queue_name, sb.consumer_group_name, sb.consumer_name
                )


def s(value: Any) -> Any:
    """Decode a bytes value from a non-``decode_responses`` client; pass through others."""
    return value.decode() if isinstance(value, bytes) else value


def decode_message(raw: bytes | str) -> dict[str, Any]:
    """Best-effort decode of a stream entry's ``data`` field into task info."""
    sb = stream_broker()
    if sb is None:
        return {}
    try:
        message = sb.formatter.loads(raw.encode() if isinstance(raw, str) else raw)
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

    Redis-specific by design - callers (the BackgroundJob/BackgroundWorker
    controllers) put this straight in API ``meta`` for the frontend to
    display as-is, so no generic UI component ever needs to know Redis
    exists.
    """
    message = _UNAVAILABLE_MESSAGES.get(reason)
    return _(message) if message else _("The data source is temporarily unavailable.")
