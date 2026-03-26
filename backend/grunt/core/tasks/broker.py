from __future__ import annotations

import structlog
from taskiq import AsyncBroker, InMemoryBroker
from taskiq_redis import RedisStreamBroker
from grunt.core.tasks.middleware import BackgroundTaskLoggingMiddleware

from grunt.config import settings

logger = structlog.get_logger()

# Global broker instance
broker: AsyncBroker

if settings.redis_url:
    broker = RedisStreamBroker(settings.redis_url).with_middlewares(
        BackgroundTaskLoggingMiddleware()
    )
    logger.info("tasks.broker_initialized", type="redis_stream", url=settings.redis_url)
else:
    # Fallback to In-Memory broker for local dev without Redis
    broker = InMemoryBroker().with_middlewares(
        BackgroundTaskLoggingMiddleware()
    )
    logger.warning("tasks.broker_initialized", type="in_memory", reason="REDIS_URL not set")


def task(*args, **kwargs):
    """Decorator to register a background task.
    
    Usage:
        @task
        async def my_task(param):
            ...
    """
    return broker.task(*args, **kwargs)
