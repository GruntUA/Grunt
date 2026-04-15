"""Tree API — endpoints for is_tree DocTypes.

GET  /docs/{doctype}/tree                — full nested tree (or subtree from root_id)
GET  /docs/{doctype}/tree/children       — direct children of a parent node
GET  /docs/{doctype}/tree/ancestors/{id} — path from node up to the root
PATCH /docs/{doctype}/tree/move/{id}     — re-parent a node
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import User
from grunt.core.document.tree import tree_service

router = GruntRouter(prefix="", tags=["docs", "tree"])


@router.get("/{doctype}/tree")
async def get_tree(
    doctype: str,
    root_id: str | None = Query(None, description="Start from this node; omit for full forest"),
    max_depth: int = Query(10, ge=1, le=50),
    fields: str | None = Query(None, description="Comma-separated extra fields to include"),
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
    nodes = await tree_service.get_tree(
        session,
        doctype,
        root_id=root_id,
        fields=parsed_fields,
        max_depth=max_depth,
    )
    return ok(nodes)


@router.get("/{doctype}/tree/children")
async def get_children(
    doctype: str,
    parent_id: str | None = Query(None, description="Parent node id; omit for root nodes"),
    fields: str | None = Query(None, description="Comma-separated extra fields to include"),
    limit: int = Query(500, ge=1, le=2000),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    """Return direct children of *parent_id* (lazy-load one level at a time).

    Each node includes a ``has_children`` boolean for rendering expand arrows.
    """
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    session = grunt._require_session()
    nodes = await tree_service.get_children(
        session,
        doctype,
        parent_id=parent_id,
        fields=parsed_fields,
        limit=limit,
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


from pydantic import BaseModel  # noqa: E402


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
