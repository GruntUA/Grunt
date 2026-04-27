"""REST endpoint for dashboard widget data computation."""

from __future__ import annotations

from typing import Any

from fastapi import Query

from grunt.api.router import GruntRouter
from grunt.api.v1.dashboard import get_dashboard_data
from grunt.api.v1.schemas.response import ok

router = GruntRouter()


@router.get("/dashboard-data/{name}")
async def dashboard_data(
    name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> dict[str, Any]:
    """Return computed widget data for a Dashboard."""
    data = await get_dashboard_data(name, date_from=date_from, date_to=date_to)
    return ok(data)
