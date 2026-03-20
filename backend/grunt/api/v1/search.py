"""Global search endpoint — searches across all DocTypes."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import get_table_name
from grunt.core.metadata.registry import doctype_registry
from grunt.core.permissions.rbac import PermissionChecker

logger = structlog.get_logger()

router = APIRouter()


@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Search across all DocTypes where user has read access.

    Returns results grouped with doctype, id, name, display_title.
    """
    results: list[dict[str, Any]] = []
    search_term = f"%{q}%"

    for dt in (await doctype_registry.list_all()):
        if dt.is_child:
            continue

        # Check read permission
        checker = PermissionChecker(dt, user)
        if not checker.check("read"):
            continue

        table_name = get_table_name(dt.module, dt.name)

        # Build search columns: name + search_fields + title_field
        search_cols: list[str] = ["name"]
        if dt.search_fields:
            search_cols.extend(dt.search_fields)
        if dt.title_field and dt.title_field not in search_cols:
            search_cols.append(dt.title_field)

        # Build WHERE clause
        conditions = " OR ".join(
            f'CAST("{col}" AS TEXT) LIKE :q' for col in search_cols
        )

        sql = (
            f'SELECT "id", "name"'
            f'{", " + chr(34) + dt.title_field + chr(34) if dt.title_field else ""}'
            f' FROM "{table_name}"'
            f" WHERE {conditions}"
            f" LIMIT :lim"
        )

        try:
            result = await session.execute(text(sql), {"q": search_term, "lim": limit})
            for row in result.mappings():
                display = str(row.get(dt.title_field, row["name"])) if dt.title_field else str(row["name"])
                results.append({
                    "doctype": dt.name,
                    "id": str(row["id"]),
                    "name": str(row["name"]),
                    "display_title": display,
                })
        except Exception as e:
            logger.debug("search.skip_doctype", doctype=dt.name, error=str(e))
            continue

        if len(results) >= limit:
            break

    return {"success": True, "data": results[:limit]}
