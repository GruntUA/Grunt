"""Dev-mode profiler whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt.config import settings


def _require_debug() -> None:
    if not settings.debug:
        grunt.throw("Not found", "NOT_FOUND")


@grunt.whitelist()
async def get_profiler_requests(limit: int = 50) -> list[dict[str, Any]]:
    """Recent requests with per-request query breakdown."""
    _require_debug()
    from grunt.db.profiler import get_recent_requests

    return get_recent_requests(limit=int(limit))


@grunt.whitelist()
async def get_slow_queries(limit: int = 100) -> list[dict[str, Any]]:
    """All slow queries from the global ring buffer."""
    _require_debug()
    from grunt.db.profiler import get_slow_queries

    return get_slow_queries(limit=int(limit))


@grunt.whitelist()
async def get_profiler_stats() -> dict[str, Any]:
    """Aggregate stats: request count, slow query count, avg/p95 duration."""
    _require_debug()
    from grunt.db.profiler import get_stats

    return get_stats()


@grunt.whitelist()
async def clear_profiler() -> bool:
    """Clear both ring buffers."""
    _require_debug()
    from grunt.db.profiler import clear_buffers

    clear_buffers()
    return True


@grunt.whitelist()
async def get_profiler_settings() -> dict[str, Any]:
    """Return current profiler runtime settings."""
    _require_debug()
    from grunt.db.profiler import get_settings

    return get_settings()


@grunt.whitelist()
async def update_profiler_settings(
    enabled: bool | None = None,
    threshold_ms: float | None = None,
    slow_request_db_ms: float | None = None,
    slow_request_ms: float | None = None,
    n1_threshold: int | None = None,
) -> dict[str, Any]:
    """Update profiler thresholds at runtime."""
    _require_debug()
    from grunt.db.profiler import (
        get_settings,
        set_enabled,
        set_n1_threshold,
        set_request_db_threshold,
        set_request_threshold,
        set_threshold,
    )

    if enabled is not None:
        set_enabled(str(enabled).lower() == "true")
    if threshold_ms is not None:
        set_threshold(max(1.0, float(threshold_ms)))
    if slow_request_db_ms is not None:
        set_request_db_threshold(max(1.0, float(slow_request_db_ms)))
    if slow_request_ms is not None:
        set_request_threshold(max(1.0, float(slow_request_ms)))
    if n1_threshold is not None:
        set_n1_threshold(int(n1_threshold))

    return get_settings()


@grunt.whitelist()
async def get_query_cache_stats() -> dict[str, Any]:
    """Return query cache runtime stats and config."""
    _require_debug()
    cache = getattr(grunt, "query_cache", None)
    if cache is None:
        return {
            "enabled": False,
            "ttl_seconds": int(settings.query_cache_ttl_seconds),
            "hits": 0,
            "misses": 0,
            "keys": 0,
        }

    stats = cache.stats()
    return {
        "enabled": bool(settings.query_cache_enabled),
        "ttl_seconds": int(settings.query_cache_ttl_seconds),
        **stats,
    }


@grunt.whitelist()
async def clear_query_cache() -> bool:
    """Clear in-memory query cache (dev helper)."""
    _require_debug()
    cache = getattr(grunt, "query_cache", None)
    if cache is not None:
        cache.clear()
    return True
