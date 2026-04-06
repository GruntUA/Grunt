from typing import Any

from fastapi import APIRouter, Depends, Query

from grunt.app import grunt
from grunt.core.auth.dependencies import grunt_context

router = APIRouter()


@router.get("/")
async def get_activity(
    limit: int = Query(50, ge=1, le=500),
    page: int = Query(1, ge=1),
    doctype: str | None = Query(None),
    user: str | None = Query(None),
    action: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    _: None = Depends(grunt_context),
) -> dict[str, Any]:
    """Return a filtered, paginated activity feed."""
    filters: dict[str, str] = {}
    if doctype:
        filters["doctype"] = doctype
    if user:
        filters["user"] = user
    if action:
        filters["action"] = action
    if date_from:
        filters["created_at__gte"] = date_from
    if date_to:
        filters["created_at__lte"] = date_to

    total = await grunt.count("ActivityLog", filters=filters)
    entries = await grunt.get_list(
        "ActivityLog",
        filters=filters,
        fields=["id", "doctype", "doc_id", "action", "user", "details", "created_at"],
        limit=limit,
        page=page,
        order_by="created_at",
        order="desc",
    )

    return {
        "success": True,
        "data": entries,
        "meta": {"total": total, "page": page, "per_page": limit, "pages": -(-total // limit)},
    }
