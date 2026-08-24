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

from grunt.api.router import GruntRouter
from grunt.api.v1.docs.utils import parse_query_filters
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.auth.dependencies import current_user
from grunt.auth.doctypes.User.user import User
from grunt.document.tree import TREE_TITLE_RESOLVERS, tree_service
from grunt.permissions.guards import read_guard, write_guard

router = GruntRouter(prefix="", tags=["docs", "tree"])


def _parse_iso_day(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()[:10]
    try:
        return str(date.fromisoformat(value))
    except ValueError:
        return None


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
    await read_guard(doctype)
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    session = grunt._require_session()

    merged_tree_filters = parse_query_filters(request)

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
    resolver = TREE_TITLE_RESOLVERS.get(doctype)
    if resolver and as_of_date:
        resolved_titles = await resolver(session, nodes, as_of_date)
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
    await read_guard(doctype)
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    session = grunt._require_session()
    merged_tree_filters = parse_query_filters(request)

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
    await read_guard(doctype)
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
    await write_guard(doctype, "write")
    session = grunt._require_session()
    doc = await tree_service.move_node(
        session,
        doctype,
        node_id,
        new_parent_id=body.new_parent_id,
        user=user,
    )
    return ok(doc)
