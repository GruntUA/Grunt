"""Child-table rows have no access rules of their own.

A row is readable when its parent document is readable; without a row to look
at, a child DocType is readable when one of the DocTypes that embed it (via a
Table field) is. Rows are never changed directly - only by saving the parent,
where its controller validates them (e.g. User guards its ``roles``).
"""

from collections.abc import Collection
from typing import Any

from grunt.query.nodes import FALSE, Cmp, Expr, Linked, and_, or_
lazy import grunt
lazy from grunt.auth.doctypes.User.user import User
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


async def child_allowed(
    user: User, doctype: Any, action: PermissionAction, doc: dict | None
) -> bool:

    if action not in ("read", "select"):
        return False
    parent_doctype = (doc or {}).get("parent_doctype")
    if doc is not None and parent_doctype:
        parent_meta = await grunt.get_meta(parent_doctype)
        if parent_meta is None:
            return False
        lookup = parent_meta.name if parent_meta.is_singleton else doc.get("parent_name")
        parent = await grunt.db.get_value(parent_doctype, lookup, "*") if lookup else None
        if parent is None:
            return False
        return await permission_checker.check(user, parent_meta, "read", parent)

    for parent_meta in await parent_doctypes(doctype.name):
        if await permission_checker.check(user, parent_meta, "read"):
            return True
    return False


async def child_predicate(columns: Collection[str], user: User, doctype: Any) -> Expr:
    """Rows whose parent document *user* may read, for list queries."""
    if "parent_doctype" not in columns or "parent_name" not in columns:
        return FALSE
    readable: list[Expr] = []
    for parent_meta in await parent_doctypes(doctype.name):
        where = await readable_predicate(user, parent_meta)
        if where is not None:
            readable.append(
                and_(
                    Cmp("parent_doctype", "eq", parent_meta.name),
                    Linked("parent_name", parent_meta.name, where),
                )
            )
    return or_(*readable)
