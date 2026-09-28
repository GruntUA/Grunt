"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from grunt.api.v1.schemas.response import ok

router = APIRouter()


@router.get("/health", tags=["health"])
async def liveness() -> dict[str, Any]:
    """Liveness probe — returns ok if the process is running."""
    return ok({"status": "ok"})


@router.get("/ready", tags=["health"])
async def readiness() -> dict[str, Any]:
    """Readiness probe — verifies DB connectivity and Redis availability."""
    checks: dict[str, str] = {}

    # Database
    try:
        from grunt.site.manager import site_manager

        site_name = site_manager.get_active_site()
        maker = site_manager.get_session_maker(site_name)
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    # Redis (optional)
    try:
        from grunt.config import settings

        if settings.redis_url:
            from grunt.utils.redis import connect

            r = connect(socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    overall = "ok" if all(v in ("ok", "not_configured") for v in checks.values()) else "degraded"
    return ok({"status": overall, "checks": checks})
