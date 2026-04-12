"""Global full-text search API.

GET  /api/v1/search?q=...&doctype=...&limit=30
POST /api/v1/search/reindex   (superadmin only — rebuild entire index)
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.core.auth.dependencies import superadmin_user
from grunt.core.search.service import search_index_service

router = GruntRouter(prefix="", tags=["search"])


@router.get("")
async def global_search(
    q: str = Query(..., min_length=2),
    doctype: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """Search across all non-child DocTypes using the full-text index."""
    from grunt.core.metadata.registry import doctype_registry
    from grunt.core.permissions.rbac import permission_checker

    raw = await search_index_service.search(
        session=grunt._require_session(),
        q=q,
        limit=limit,
        doctype=doctype,
    )

    user = grunt._require_user()
    # Check read permission per doctype (superadmin bypasses natively)
    allowed_doctypes: dict[str, bool] = {}
    for r in raw:
        dt_name = r["doctype"]
        if dt_name not in allowed_doctypes:
            try:
                dt = await doctype_registry.get(dt_name)
                allowed_doctypes[dt_name] = await permission_checker.check(user, dt, "read")
            except Exception:  # noqa: BLE001
                allowed_doctypes[dt_name] = False

    results = [
        {
            "doctype": r["doctype"],
            "id": r["doc_id"],
            "name": r["doc_name"],
            "display_title": r.get("title") or r.get("doc_name", ""),
            "module": r.get("module", ""),
        }
        for r in raw
        if allowed_doctypes.get(r["doctype"], False)
    ]
    return ok(results)


@router.get("/rebuild-index")
async def rebuild_search_index(
    _: Any = Depends(superadmin_user),
) -> dict[str, Any]:
    """Rebuild the entire search index from scratch. Superadmin only."""
    session = grunt._require_session()
    count = await search_index_service.reindex_all(session, grunt._require_engine())
    return ok(indexed=count)
