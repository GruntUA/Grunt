"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()


@router.get("/health", tags=["health"])
async def liveness() -> dict:
    """Liveness probe — returns ok if the process is running."""
    return {"status": "ok"}


@router.get("/ready", tags=["health"])
async def readiness() -> dict:
    """Readiness probe — verifies DB connectivity and Redis availability."""
    checks: dict[str, str] = {}

    # Database
    try:
        from grunt.core.site.manager import site_manager  # noqa: PLC0415

        site_name = site_manager.get_active_site()
        maker = site_manager.get_session_maker(site_name)
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    # Redis (optional)
    try:
        from grunt.config import settings  # noqa: PLC0415

        if settings.redis_url:
            import redis.asyncio as aioredis  # noqa: PLC0415

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    status = "ok" if all(v in ("ok", "not_configured") for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
