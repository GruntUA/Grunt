"""Single entry point for Redis clients.

redis-py ≥ 7 sends ``CLIENT MAINT_NOTIFICATIONS`` on every new connection
(RESP3), which only Redis ≥ 8.2 / Redis Cloud understands - on older servers
each connect logs "Failed to enable maintenance notifications". Grunt talks
to a single standalone Redis, so the feature is switched off for every client.
"""

import asyncio
import time
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.maint_notifications import MaintNotificationsConfig

from grunt.log import log
lazy from grunt.config import settings


def connection_options() -> dict[str, Any]:
    """Keyword args every Redis client/pool must get (also for taskiq-redis)."""

    return {"maint_notifications_config": MaintNotificationsConfig(enabled=False)}


def connect(url: str | None = None, **kwargs: Any) -> Redis:
    """Async Redis client for ``url`` (default: ``settings.redis_url``)."""

    if url is None:
        url = settings.redis_url
    if not url:
        raise RuntimeError("REDIS_URL is not configured")
    return aioredis.from_url(url, **connection_options(), **kwargs)


class Shared:
    """One client per process for short commands, with a back-off after a failure.

    Caches, the rate limiter and the idempotency store all talk to Redis on
    the request path: they share this client (its own connection pool) instead
    of opening a connection per call. After an error :meth:`failed` turns
    Redis off for ``retry_seconds``, then the next call tries again - callers
    fall back to their in-process store meanwhile, and a Redis restart does
    not leave a process without Redis until its own restart.

    The client is bound to the event loop that created it; a new loop (tests,
    the CLI's ``asyncio.run``) gets a new client.
    """

    retry_seconds = 30.0

    def __init__(self) -> None:
        self._client: Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._retry_at = 0.0

    def get(self) -> Redis | None:
        """The client, or None without REDIS_URL or during the back-off."""
        if not settings.redis_url or time.monotonic() < self._retry_at:
            return None
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop:
            self._client = connect(socket_connect_timeout=1, socket_timeout=2)
            self._loop = loop
        return self._client

    def failed(self, event: str, exc: BaseException) -> None:
        """Log a failed command and pause Redis for ``retry_seconds``."""
        self._retry_at = time.monotonic() + self.retry_seconds
        log.warning(event, error=str(exc))

    async def aclose(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()


shared = Shared()
