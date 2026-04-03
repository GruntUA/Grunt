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
    limit: int = Query(30, ge=1, le=100),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Search across all non-child DocTypes using the full-text index."""
    results = await search_index_service.search(
        session=session,
        q=q,
        limit=limit,
        doctype=doctype,
    )
    return results


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
