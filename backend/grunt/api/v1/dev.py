"""Dev-mode profiler API — available only when settings.debug is True."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from grunt.config import settings

router = APIRouter(prefix="/dev", tags=["dev"])


def _require_debug() -> None:
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/profiler/requests")
def profiler_requests(limit: int = Query(50, ge=1, le=200)):
    """Recent requests with per-request query breakdown."""
    _require_debug()
    from grunt.core.db.profiler import get_recent_requests  # noqa: PLC0415
    return {"data": get_recent_requests(limit=limit)}


@router.get("/profiler/slow-queries")
def profiler_slow_queries(limit: int = Query(100, ge=1, le=500)):
    """All slow queries from the global ring buffer."""
    _require_debug()
    from grunt.core.db.profiler import get_slow_queries  # noqa: PLC0415
    return {"data": get_slow_queries(limit=limit)}


@router.get("/profiler/stats")
def profiler_stats():
    """Aggregate stats: request count, slow query count, avg/p95 duration."""
    _require_debug()
    from grunt.core.db.profiler import get_stats  # noqa: PLC0415
    return {"data": get_stats()}


@router.delete("/profiler/clear")
def profiler_clear():
    """Clear both ring buffers."""
    _require_debug()
    from grunt.core.db.profiler import clear_buffers  # noqa: PLC0415
    clear_buffers()
    return {"data": {"cleared": True}}


class ProfilerSettings(BaseModel):
    enabled: bool | None = None
    threshold_ms: float | None = None


@router.get("/profiler/settings")
def profiler_get_settings():
    """Return current profiler runtime settings."""
    _require_debug()
    from grunt.core.db.profiler import get_settings  # noqa: PLC0415
    return {"data": get_settings()}


@router.put("/profiler/settings")
def profiler_update_settings(body: ProfilerSettings):
    """Update enabled flag and/or slow-query threshold."""
    _require_debug()
    from grunt.core.db.profiler import set_enabled, set_threshold, get_settings  # noqa: PLC0415
    if body.enabled is not None:
        set_enabled(body.enabled)
    if body.threshold_ms is not None:
        set_threshold(max(1.0, body.threshold_ms))
    return {"data": get_settings()}
