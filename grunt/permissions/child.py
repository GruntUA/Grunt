"""Child-table rows have no access rules of their own.

A row is readable when its parent document is readable; without a row to look
at, a child DocType is readable when one of the DocTypes that embed it (via a
Table field) is. Rows are never changed directly - only by saving the parent,
where its controller validates them (e.g. User guards its ``roles``).
"""

from collections.abc import Collection, Mapping
from typing import Any

from grunt.query.nodes import FALSE, Cmp, Expr, Linked, and_, or_
lazy import grunt
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.permissions.rbac import permission_checker
lazy from grunt.permissions.reference import readable_predicate
lazy from grunt.permissions.types import PermissionAction


def is_child(doctype: Any) -> bool:
    return getattr(getattr(doctype, "doc", doctype), "is_child", False) is True


async def parent_doctypes(child_name: str) -> list[Any]:
    """Metas of the DocTypes whose Table fields hold *child_name* rows."""

    names = {
        dt.name
        for dt in await doctype_registry.list_all()
        if not dt.is_child
        and any(f.has_trait("table") and f.options == child_name for f in dt.fields)
    }
    metas = [await grunt.get_meta(name) for name in sorted(names)]
    return [m for m in metas if m is not None]


async def child_allowed(user: str | None, doctype: Any, action: PermissionAction) -> bool:
    """DocType-level: a child DocType is readable when one of the DocTypes that
    embed it is. A single row is decided by :func:`child_predicate`."""
    if action not in ("read", "select"):
        return False
    for parent_meta in await parent_doctypes(doctype.name):
        if await permission_checker.check(parent_meta, "read", user=user):
            return True
    return False


async def child_predicate(
    columns: Collection[str],
    user: str | None,
    doctype: Any,
    *,
    row: Mapping[str, Any] | None = None,
) -> Expr:
    """Rows whose parent document *user* may read. With *row* only its own
    parent DocType is considered (exact for that row)."""
    if "parent_doctype" not in columns or "parent_name" not in columns:
        return FALSE
    parents = await parent_doctypes(doctype.name)
    if row is not None:
        parents = [p for p in parents if p.name == row.get("parent_doctype")]
    readable: list[Expr] = []
    for parent_meta in parents:
        where = await readable_predicate(user, parent_meta)
        if where is not None:
            readable.append(
                and_(
                    Cmp("parent_doctype", "eq", parent_meta.name),
                    Linked("parent_name", parent_meta.name, where),
                )
            )
    return or_(*readable)
