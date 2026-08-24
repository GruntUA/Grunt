"""Tree RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_tree
RPC: grunt.document.base.Document.get_tree_children   — children of a node (or root)
RPC: grunt.document.base.Document.get_tree_ancestors  — path from node up to the root
RPC: grunt.document.base.Document.move_tree_node       — re-parent a node
"""

from __future__ import annotations

from datetime import date
from typing import Any

import grunt
from grunt.document.tree import TREE_TITLE_RESOLVERS, tree_service
from grunt.permissions.guards import read_guard, write_guard


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


class DocumentTreeRPCMixin:
    """Tree operations for ``is_tree`` DocTypes, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_tree(
        doctype: str,
        root_id: str | None = None,
        max_depth: int = 10,
        fields: list[str] | None = None,
        as_of: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the full tree (or subtree from *root_id*) as nested dicts with ``children``."""
        from grunt.app import grunt as grunt_app

        await read_guard(doctype)
        session = grunt_app._require_session()

        nodes = await tree_service.get_tree(
            session,
            doctype,
            root_id=root_id,
            fields=fields,
            max_depth=max_depth,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        as_of_date = _parse_iso_day(as_of)
        resolver = TREE_TITLE_RESOLVERS.get(doctype)
        if resolver and as_of_date:
            resolved_titles = await resolver(session, nodes, as_of_date)
            _apply_display_titles(nodes, resolved_titles)

        return nodes

    @staticmethod
    @grunt.whitelist()
    async def get_tree_children(
        doctype: str,
        node_id: str | None = None,
        fields: list[str] | None = None,
        per_page: int = 500,
        sort_by: str | None = None,
        sort_order: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return direct children of *node_id* (omit for root nodes), one level at a time.

        Each node includes a ``has_children`` boolean for rendering expand arrows.
        """
        from grunt.app import grunt as grunt_app

        await read_guard(doctype)
        session = grunt_app._require_session()

        return await tree_service.get_children(
            session,
            doctype,
            parent_id=node_id,
            fields=fields,
            limit=per_page,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @staticmethod
    @grunt.whitelist()
    async def get_tree_ancestors(
        doctype: str,
        node_id: str,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the breadcrumb path from the root down to *node_id*'s parent.

        Ordered from root → direct parent (closest ancestor last).
        """
        from grunt.app import grunt as grunt_app

        await read_guard(doctype)
        session = grunt_app._require_session()
        return await tree_service.get_ancestors(session, doctype, node_id, fields=fields)

    @staticmethod
    @grunt.whitelist()
    async def move_tree_node(
        doctype: str, node_id: str, new_parent_id: str | None = None
    ) -> dict[str, Any]:
        """Re-parent *node_id* to *new_parent_id* (or make it a root node if ``None``).

        Returns the updated document. Raises 409 if the move would create a cycle.
        """
        from grunt.app import grunt as grunt_app

        await write_guard(doctype, "write")
        session = grunt_app._require_session()
        return await tree_service.move_node(
            session,
            doctype,
            node_id,
            new_parent_id=new_parent_id,
            user=grunt.get_user(),
        )
