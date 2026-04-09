from typing import Any

from fastapi import Query

from grunt.api.router import GruntRouter
from grunt.app import grunt

router = GruntRouter(prefix="", tags=["activity"])


@router.get("")
async def list_activity(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    doctype: str | None = Query(None),
    doc_id: str | None = Query(None),
    user: str | None = Query(None),
    action: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> dict[str, Any]:
    """Return a filtered, paginated activity feed."""
    filters: dict[str, str] = {}
    if doctype:
        filters["doctype"] = doctype
    if doc_id:
        filters["doc_id"] = doc_id
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
        limit=per_page,
        page=page,
        order_by="created_at",
        order="desc",
    )

    return {
        "success": True,
        "data": entries,
        "meta": {"total": total, "page": page, "per_page": per_page, "pages": -(-total // per_page)},
    }
