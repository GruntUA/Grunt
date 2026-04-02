from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from grunt.core.db.session import get_session
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.metadata.registry import doctype_registry
from grunt.core.metadata.compiler import compile_doctype_to_table
from typing import Any

router = APIRouter()

@router.get("/")
async def get_activity(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return a global activity feed."""
    table = compile_doctype_to_table(doctype_registry._doctypes["ActivityLog"])
    
    q = (
        select(table)
        .order_by(desc(table.c.created_at))
        .limit(limit)
    )
    
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
    
    return {"success": True, "data": data}
