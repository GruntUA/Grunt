from __future__ import annotations

import structlog
from taskiq import AsyncBroker, InMemoryBroker, SmartRetryMiddleware
from taskiq_redis import RedisStreamBroker
from grunt.core.tasks.middleware import BackgroundTaskLoggingMiddleware

from grunt.config import settings

logger = structlog.get_logger()

# Default retry configuration
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 60  # seconds

# Global broker instance
broker: AsyncBroker

_retry_middleware = SmartRetryMiddleware(
    default_retry_count=_DEFAULT_MAX_RETRIES,
    default_delay=_DEFAULT_RETRY_DELAY,
    default_retry_label=False,  # Tasks must opt-in via retry_on_error=True label
)

if settings.redis_url:
    broker = RedisStreamBroker(settings.redis_url).with_middlewares(
        BackgroundTaskLoggingMiddleware(),
        _retry_middleware,
    )
    logger.info("tasks.broker_initialized", type="redis_stream", url=settings.redis_url)
else:
    # Fallback to In-Memory broker for local dev without Redis
    broker = InMemoryBroker().with_middlewares(
        BackgroundTaskLoggingMiddleware(),
        _retry_middleware,
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


def retryable_task(max_retries: int = _DEFAULT_MAX_RETRIES, delay: int = _DEFAULT_RETRY_DELAY):
    """Decorator to register a background task with automatic retry on failure.

    Uses SmartRetryMiddleware to re-enqueue the task after ``delay`` seconds,
    up to ``max_retries`` attempts total.

    Usage:
        @retryable_task()
        async def my_task(param):
            ...

        @retryable_task(max_retries=5, delay=30)
        async def important_task():
            ...
    """
    def decorator(func):
        return broker.task(
            retry_on_error=True,
            max_retries=max_retries,
            delay=delay,
        )(func)
    return decorator
