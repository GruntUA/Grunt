from typing import Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, String, cast
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, get_session
from grunt.core.auth.models import GruntUser
from grunt.core.metadata.registry import doctype_registry
from grunt.core.metadata.compiler import compile_doctype_to_table
router = APIRouter()

@router.get("")
async def global_search(
    q: str = Query(..., min_length=2),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session)
) -> List[dict]:
    """Search across all major DocTypes."""
    results = []
    all_doctypes = await doctype_registry.list_all()
    
    # We'll limit search to top DocTypes or those with search_fields
    # To avoid 100+ queries, we might want to prioritize
    searchable_doctypes = [dt for dt in all_doctypes if not dt.is_child]
    
    for dt in searchable_doctypes:
        # Check permissions - briefly
        # Ideally we'd use a more efficient way, but for now we search and then filter or search directly
        table = compile_doctype_to_table(dt)
        
        search_cols = []
        # Always search 'name'
        if "name" in table.c:
            search_cols.append(table.c.name)
            
        # Search title field
        title_field = dt.title_field or "name"
        if title_field in table.c and title_field != "name":
            search_cols.append(table.c[title_field])
            
        # Search additional fields
        for sf in dt.search_fields:
            if sf in table.c and sf not in (title_field, "name"):
                search_cols.append(table.c[sf])
        
        if not search_cols:
            continue
            
        # Build query
        filters = [cast(col, String).ilike(f"%{q}%") for col in search_cols]
        stmt = select(table).where(or_(*filters)).limit(10)
        
        try:
            res = await session.execute(stmt)
            rows = res.fetchall()
            
            for row in rows:
                data = dict(row._mapping)
                results.append({
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "title": data.get(title_field) or data.get("name"),
                    "doctype": dt.name,
                    "doctype_label": dt.label,
                    "module": dt.module,
                    "subtitle": dt.name if title_field != "name" else dt.label
                })
        except Exception:
            # Skip tables that might have issues
            continue
            
        if len(results) >= 50:
            break
            
    return results
