from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

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
    session: AsyncSession = Depends(get_session),
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return a filtered, paginated activity feed."""
    table = compile_doctype_to_table(doctype_registry._doctypes["ActivityLog"])

    conditions = []
    if doctype:
        conditions.append(table.c.doctype == doctype)
    if user:
        conditions.append(table.c.user == user)
    if action:
        conditions.append(table.c.action == action)
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            conditions.append(table.c.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            conditions.append(table.c.created_at <= dt)
        except ValueError:
            pass

    where = and_(*conditions) if conditions else None

    # Total count
    from sqlalchemy import func
    count_q = select(func.count()).select_from(table)
    if where is not None:
        count_q = count_q.where(where)
    total = (await session.execute(count_q)).scalar() or 0

    # Data
    offset = (page - 1) * limit
    q = select(table).order_by(desc(table.c.created_at)).limit(limit).offset(offset)
    if where is not None:
        q = q.where(where)

    result = await session.execute(q)
    entries = result.mappings().all()

    data = [
        {
            "id": e["id"],
            "doctype": e["doctype"],
            "doc_id": e["doc_id"],
            "action": e["action"],
            "user": e["user"],
            "details": e["details"],
            "created_at": e["created_at"].isoformat() if e["created_at"] else None,
        }
        for e in entries
    ]

    return {
        "success": True,
        "data": data,
        "meta": {"total": total, "page": page, "per_page": limit, "pages": -(-total // limit)},
    }
