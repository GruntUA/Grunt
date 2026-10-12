"""REST endpoints for Page widget data computation."""

from __future__ import annotations

from typing import Any

from fastapi import Query

import grunt
from grunt.api.router import GruntRouter
from grunt.api.v1.dashboard import get_dashboard_data, get_page_data
from grunt.api.v1.schemas.response import ok

router = GruntRouter()


async def _sign(data: Any) -> Any:
    """Sign file URLs in widget data for files the current user may read (widget
    rows can carry Attach/Image fields); see grunt.storage.signing."""
    from grunt.storage.signing import sign_authorized_file_urls

    return await sign_authorized_file_urls(data, grunt.get_user())


@router.get("/page-data/{name}")
async def page_data(
    name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> dict[str, Any]:
    """Return computed widget data for a Page."""
    data = await get_page_data(name, date_from=date_from, date_to=date_to)
    return ok(await _sign(data))


@router.get("/dashboard-data/{name}")
async def dashboard_data(
    name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> dict[str, Any]:
    """Return computed widget data for a Dashboard."""
    data = await get_dashboard_data(name, date_from=date_from, date_to=date_to)
    return ok(await _sign(data))
