"""Single entry point for Redis clients.

redis-py ≥ 7 sends ``CLIENT MAINT_NOTIFICATIONS`` on every new connection
(RESP3), which only Redis ≥ 8.2 / Redis Cloud understands — on older servers
each connect logs "Failed to enable maintenance notifications". Grunt talks
to a single standalone Redis, so the feature is switched off for every client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis.asyncio import Redis


def connection_options() -> dict[str, Any]:
    """Keyword args every Redis client/pool must get (also for taskiq-redis)."""
    from redis.maint_notifications import MaintNotificationsConfig

    return {"maint_notifications_config": MaintNotificationsConfig(enabled=False)}


def connect(url: str | None = None, **kwargs: Any) -> Redis:
    """Async Redis client for ``url`` (default: ``settings.redis_url``)."""
    import redis.asyncio as aioredis

    if url is None:
        from grunt.config import settings

        url = settings.redis_url
    return aioredis.from_url(url, **connection_options(), **kwargs)
