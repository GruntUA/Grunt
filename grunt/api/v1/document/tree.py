"""Tree RPC methods (``/api/v1/method/...``).

RPC: grunt.api.v1.document.tree.get_tree
RPC: grunt.api.v1.document.tree.get_tree_children - children of a node (or root)
RPC: grunt.api.v1.document.tree.get_tree_ancestors - path from node up to the root
RPC: grunt.api.v1.document.tree.move_tree_node - re-parent a node
"""

from datetime import date
from typing import Any

from sqlalchemy import select

from grunt.api.context import whitelist
from grunt.auth.current import acting_user
from grunt.document.tree import TREE_TITLE_RESOLVERS, tree_service
from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import require_session
from grunt.metadata.registry import doctype_registry
from grunt.permissions.guards import write_guard
from grunt.permissions.query import read_predicate
from grunt.permissions.rbac import permission_checker
from grunt.permissions.roles import role_access
from grunt.query.nodes import TRUE
from grunt.query.sql import where


async def _tree_read_gate(doctype: str) -> tuple[Any, list[str] | None]:
    """Permission gate for the read-only tree RPCs.

    Full ``read`` -> unrestricted (returns ``(dt, None)``). Only ``select`` ->
    the caller must limit nodes to identifier columns and ignore ad-hoc
    filters, so returns ``(dt, [name, parent_field, title_field])``. Neither ->
    a 403 naming the DocType.
    """
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = acting_user()
    access = await role_access(dt.doc, user.email)

    # An explicit ``select`` grant (without unrestricted ``read``) limits the
    # tree to identifier columns - even when the user also has a row-scoped
    # ``read`` that check(user, dt, "read") would otherwise wave through.
    if not access.has_unrestricted_read and access.has_explicit_select:
        parent_field = getattr(dt, "tree_parent_field", None) or "parent"
        title_field = getattr(dt, "tree_title_field", None) or getattr(dt, "title_field", None)
        allowed = ["name", parent_field]
        if title_field and title_field not in allowed:
            allowed.append(title_field)
        return dt, allowed

    if await permission_checker.check(dt.doc, "read", user=user.email):
        return dt, None
    await permission_checker.require(dt.doc, "select", user=user.email)  # raises 403
    return dt, None  # unreachable - require() raised


async def _tree_row_scope(dt: Any, restricted: list[str] | None) -> Any | None:
    """``SELECT name`` of the nodes the current user may see, or ``None`` when
    nothing narrows them.

    The same row-level rules the list applies - a role's ``match``, shares and
    User Permissions - so a tree (list panel, tree view, Link picker) never
    shows more than the list does. The select-only path stays unfiltered, like
    the Link-search identifier path.
    """
    if restricted is not None:
        return None

    user = acting_user()
    table = dt.table
    readable = await read_predicate(user.email, dt)
    return None if readable == TRUE else await where(select(table.c.name), readable, table, dt.name)


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


@whitelist()
async def get_tree(
    doctype: str,
    root_id: str | None = None,
    max_depth: int = 10,
    fields: list[str] | None = None,
    as_of: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    filters: dict[str, Any] | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return the full tree (or subtree from *root_id*) as nested dicts with ``children``."""

    dt, restricted = await _tree_read_gate(doctype)
    if restricted is not None:
        # select-only grant: identifier columns, no ad-hoc filters/search
        fields, filters, search = restricted, None, None
    scope = await _tree_row_scope(dt, restricted)
    session = require_session()

    nodes = await tree_service.get_tree(
        session,
        doctype,
        root_id=root_id,
        fields=fields,
        max_depth=max_depth,
        filters=filters,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        scope=scope,
    )

    as_of_date = _parse_iso_day(as_of)
    resolver = TREE_TITLE_RESOLVERS.get(doctype)
    if resolver and as_of_date:
        resolved_titles = await resolver(session, nodes, as_of_date)
        _apply_display_titles(nodes, resolved_titles)

    return nodes


@whitelist()
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

    dt, restricted = await _tree_read_gate(doctype)
    if restricted is not None:
        fields, filters = restricted, None
    scope = await _tree_row_scope(dt, restricted)
    session = require_session()

    return await tree_service.get_children(
        session,
        doctype,
        parent_id=node_id,
        fields=fields,
        limit=per_page,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        scope=scope,
    )


@whitelist()
async def get_tree_ancestors(
    doctype: str,
    node_id: str,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the breadcrumb path from the root down to *node_id*'s parent.

    Ordered from root -> direct parent (closest ancestor last).
    """

    dt, restricted = await _tree_read_gate(doctype)
    if restricted is not None:
        fields = restricted
    scope = await _tree_row_scope(dt, restricted)
    session = require_session()
    return await tree_service.get_ancestors(session, doctype, node_id, fields=fields, scope=scope)


@whitelist()
async def move_tree_node(
    doctype: str, node_id: str, new_parent_id: str | None = None
) -> dict[str, Any]:
    """Re-parent *node_id* to *new_parent_id* (or make it a root node if ``None``).

    Returns the updated document. Raises 409 if the move would create a cycle.
    """

    await write_guard(doctype, "write")
    session = require_session()
    return await tree_service.move_node(
        session,
        doctype,
        node_id,
        new_parent_id=new_parent_id,
    )
