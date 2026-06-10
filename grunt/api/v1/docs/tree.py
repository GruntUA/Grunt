"""Tree API — endpoints for is_tree DocTypes.

GET  /docs/{doctype}/tree                — full nested tree (or subtree from root_id)
GET  /docs/{doctype}/tree/children       — direct children of a parent node
GET  /docs/{doctype}/tree/ancestors/{id} — path from node up to the root
PATCH /docs/{doctype}/tree/move/{id}     — re-parent a node
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.auth.dependencies import current_user
from grunt.auth.doctypes.User.user import User
from grunt.document.tree import tree_service
from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry

router = GruntRouter(prefix="", tags=["docs", "tree"])


def _parse_iso_day(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()[:10]
    try:
        return str(date.fromisoformat(value))
    except ValueError:
        return None


def _flatten_tree_ids(nodes: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    stack = list(nodes)
    while stack:
        node = stack.pop()
        node_id = node.get("name")
        if isinstance(node_id, str) and node_id:
            ids.append(node_id)
        children = node.get("children") or []
        if isinstance(children, list):
            stack.extend(children)
    return ids


def _apply_display_titles(nodes: list[dict[str, Any]], resolved_titles: dict[str, str]) -> None:
    stack = list(nodes)
    while stack:
        node = stack.pop()
        node_id = node.get("name")
        if isinstance(node_id, str) and node_id in resolved_titles:
            node["display_title"] = resolved_titles[node_id]
        children = node.get("children") or []
        if isinstance(children, list):
            stack.extend(children)


async def _resolve_department_titles_on_date(
    session: Any,
    nodes: list[dict[str, Any]],
    as_of: str,
) -> dict[str, str]:
    dept_ids = _flatten_tree_ids(nodes)
    if not dept_ids:
        return {}

    dept_dt = await doctype_registry.get("Department")
    dept_table = compile_doctype_to_table(dept_dt)
    history_dt = await doctype_registry.get("DepartmentHistory")
    history_table = compile_doctype_to_table(history_dt)

    dept_rows = await session.execute(
        select(dept_table.c.name, dept_table.c.title).where(dept_table.c.name.in_(dept_ids))
    )
    current_titles = {str(r[0]): str(r[1] or r[0]) for r in dept_rows.fetchall()}

    history_rows = await session.execute(
        select(
            history_table.c.parent_name,
            history_table.c.change_type,
            history_table.c.effective_date,
            history_table.c.old_name,
        ).where(history_table.c.parent_name.in_(dept_ids))
    )

    by_parent: dict[str, list[dict[str, Any]]] = {}
    for parent_name, change_type, effective_date, old_name in history_rows.fetchall():
        pid = str(parent_name or "")
        if not pid:
            continue
        by_parent.setdefault(pid, []).append(
            {
                "change_type": change_type,
                "effective_date": effective_date,
                "old_name": old_name,
            }
        )

    resolved: dict[str, str] = {}
    for dept_id in dept_ids:
        fallback = current_titles.get(dept_id, dept_id)
        history = by_parent.get(dept_id, [])
        if not history:
            resolved[dept_id] = fallback
            continue

        renames = sorted(
            [
                h
                for h in history
                if h.get("change_type") == "Переймення" and h.get("effective_date")
            ],
            key=lambda h: str(h["effective_date"])[:10],
        )

        title = fallback
        for rename in renames:
            if str(rename["effective_date"])[:10] > as_of:
                title = str(rename.get("old_name") or fallback)
                break
        resolved[dept_id] = title

    return resolved


@router.get("/{doctype}/tree")
async def get_tree(
    doctype: str,
    request: Request,
    root_id: str | None = Query(None, description="Start from this node; omit for full forest"),
    max_depth: int = Query(10, ge=1, le=50),
    fields: str | None = Query(None, description="Comma-separated extra fields to include"),
    as_of: str | None = Query(None, description="ISO date (YYYY-MM-DD) for historical labels"),
    sort_by: str | None = Query(None, description="Field name used to sort tree nodes"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Tree sort direction"),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    """Return the full tree (or subtree) as nested dicts with ``children`` arrays.

    Example response::

        {
          "success": true,
          "data": [
            {
              "id": "...",
              "name": "Electronics",
              "parent_category": null,
              "children": [
                {"id": "...", "name": "Phones", "children": [], ...}
              ]
            }
          ]
        }
    """
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    session = grunt._require_session()

    # Parse fast_filter[field__op]=value and filter[field__op]=value from query params.
    # Explicit filter[...] overrides fast_filter[...] for the same key.
    merged_tree_filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("fast_filter[") and key.endswith("]"):
            merged_tree_filters[key[12:-1]] = value
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            merged_tree_filters[key[7:-1]] = value

    nodes = await tree_service.get_tree(
        session,
        doctype,
        root_id=root_id,
        fields=parsed_fields,
        max_depth=max_depth,
        filters=merged_tree_filters if merged_tree_filters else None,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    as_of_date = _parse_iso_day(as_of)
    if doctype == "Department" and as_of_date:
        resolved_titles = await _resolve_department_titles_on_date(session, nodes, as_of_date)
        _apply_display_titles(nodes, resolved_titles)

    return ok(nodes)


@router.get("/{doctype}/tree/children")
async def get_children(
    doctype: str,
    request: Request,
    parent_id: str | None = Query(None, description="Parent node id; omit for root nodes"),
    fields: str | None = Query(None, description="Comma-separated extra fields to include"),
    limit: int = Query(500, ge=1, le=2000),
    sort_by: str | None = Query(None, description="Field name used to sort direct children"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Children sort direction"),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    """Return direct children of *parent_id* (lazy-load one level at a time).

    Each node includes a ``has_children`` boolean for rendering expand arrows.
    """
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    session = grunt._require_session()
    merged_tree_filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("fast_filter[") and key.endswith("]"):
            merged_tree_filters[key[12:-1]] = value
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            merged_tree_filters[key[7:-1]] = value

    nodes = await tree_service.get_children(
        session,
        doctype,
        parent_id=parent_id,
        fields=parsed_fields,
        limit=limit,
        filters=merged_tree_filters if merged_tree_filters else None,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ok(nodes)


@router.get("/{doctype}/tree/ancestors/{node_id}")
async def get_ancestors(
    doctype: str,
    node_id: str,
    fields: str | None = Query(None, description="Comma-separated extra fields to include"),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    """Return the breadcrumb path from the root down to *node_id*'s parent.

    Ordered from root → direct parent (closest ancestor last).
    """
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    session = grunt._require_session()
    ancestors = await tree_service.get_ancestors(
        session,
        doctype,
        node_id,
        fields=parsed_fields,
    )
    return ok(ancestors)


class MoveNodeRequest:
    pass


class MoveNodeBody(BaseModel):
    new_parent_id: str | None = None


@router.patch("/{doctype}/tree/move/{node_id}")
async def move_node(
    doctype: str,
    node_id: str,
    body: MoveNodeBody,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Re-parent *node_id* to *new_parent_id* (or make it a root node if ``null``).

    Returns the updated document.  Raises 409 if the move would create a cycle.
    """
    session = grunt._require_session()
    doc = await tree_service.move_node(
        session,
        doctype,
        node_id,
        new_parent_id=body.new_parent_id,
        user=user,
    )
    return ok(doc)
