"""Global full-text search API.

GET  /api/v1/search?q=...&doctype=...&limit=30
POST /api/v1/search/reindex   (superadmin only — rebuild entire index)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.dependencies import current_user, get_session
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_engine
from grunt.core.search.service import search_index_service

router = APIRouter()


@router.get("")
async def global_search(
    q: str = Query(..., min_length=2),
    doctype: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Search across all non-child DocTypes using the full-text index."""
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

    raw = await search_index_service.search(
        session=session,
        q=q,
        limit=limit,
        doctype=doctype,
    )

    # Check read permission per doctype (superadmin bypasses via permission_checker)
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
    return {"success": True, "data": results}


@router.post("/reindex", status_code=status.HTTP_200_OK)
async def reindex(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Rebuild the entire search index from scratch. Superadmin only."""
    if not user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin required")

    count = await search_index_service.reindex_all(session, engine)
    return {"success": True, "indexed": count}
