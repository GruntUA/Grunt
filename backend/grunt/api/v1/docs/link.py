"""Link field search endpoint.

Provides a dedicated search API optimised for Link field dropdowns:
  - Always searches `name` AND `title_field` (OR condition).
  - Also includes `search_fields` declared on the DocType.
  - Accepts arbitrary extra filters (from ``link_filters`` on DocField or JS).
  - Returns a compact payload: [{id, name, title, subtitle}].
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, Query
from sqlalchemy import or_, select

from grunt.api.router import GruntRouter
from grunt.api.v1.docs.utils import get_doc_service
from grunt.api.v1.schemas.response import ok
from grunt.core.auth.dependencies import current_user
from grunt.core.doctypes.user.user import User
from grunt.core.document.query import _apply_filters
from grunt.core.document.service import DocumentService
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

router = GruntRouter()


@router.get("/{doctype}/link_search")
async def link_search(
    doctype: str,
    q: str = Query(default="", description="Search string"),
    filters: str = Query(default="{}", description="JSON-encoded extra filters"),
    page_length: int = Query(default=10, ge=1, le=100),
    user: User = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Search documents for a Link field dropdown."""
    dt = await doctype_registry.get(doctype)

    # Virtual DocType — delegate to its controller's get_list
    if dt.is_virtual:
        from grunt.core.document.virtual import _get_virtual_controller  # noqa: PLC0415

        ctrl = _get_virtual_controller(doctype, user)
        result = await ctrl.get_list(search=q, page=1, per_page=page_length)
        title_field = dt.title_field or "name"
        items = []
        for row in result.get("data", []):
            name_val = str(row.get("name") or row.get("id") or "")
            title_val = str(row.get(title_field) or name_val)
            items.append({
                "id": str(row.get("id") or name_val),
                "name": name_val,
                "title": title_val,
                "subtitle": name_val if title_val != name_val else None,
            })
        return ok(items)

    table = compile_doctype_to_table(dt)

    title_field: str = (dt.title_field or "name") if hasattr(dt, "title_field") else "name"

    # ── Columns to fetch ─────────────────────────────────────────────────────
    cols_needed = {"id", "name"}
    if title_field and title_field != "name" and title_field in table.c:
        cols_needed.add(title_field)
    # Include search_fields for display as subtitle
    search_fields: list[str] = list(getattr(dt, "search_fields", None) or [])
    for sf in search_fields:
        if sf in table.c:
            cols_needed.add(sf)

    cols = [table.c[c] for c in cols_needed if c in table.c]

    stmt = select(*cols)

    # ── Parse extra filters ───────────────────────────────────────────────────
    try:
        extra_filters: dict[str, str] = json.loads(filters) if filters and filters != "{}" else {}
    except (json.JSONDecodeError, ValueError):
        extra_filters = {}

    if extra_filters:
        stmt = _apply_filters(stmt, table, extra_filters)

    # ── Search conditions ─────────────────────────────────────────────────────
    if q:
        search_term = f"%{q}%"
        conditions = [table.c.name.ilike(search_term)]
        if title_field and title_field != "name" and title_field in table.c:
            conditions.append(table.c[title_field].ilike(search_term))
        for sf in search_fields:
            if sf != "name" and sf != title_field and sf in table.c:
                conditions.append(table.c[sf].ilike(search_term))
        stmt = stmt.where(or_(*conditions))

    stmt = stmt.limit(page_length)

    session = svc.session
    result = await session.execute(stmt)
    rows = [dict(r._mapping) for r in result.all()]

    # ── Shape response ────────────────────────────────────────────────────────
    items = []
    for row in rows:
        name_val = str(row.get("name") or row.get("id") or "")
        title_val = str(row.get(title_field) or name_val) if title_field else name_val
        subtitle_val = name_val if title_val != name_val else None
        items.append(
            {
                "id": str(row.get("id") or name_val),
                "name": name_val,
                "title": title_val,
                "subtitle": subtitle_val,
            }
        )

    return ok(items)
