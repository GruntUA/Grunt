"""Child-table rows have no access rules of their own.

A row is readable when its parent document is readable; without a row to look
at, a child DocType is readable when one of the DocTypes that embed it (via a
Table field) is. Rows are never changed directly - only by saving the parent,
where its controller validates them (e.g. User guards its ``roles``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, false, or_

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, Table

    from grunt.auth.doctypes.User.user import User
    from grunt.permissions.types import PermissionAction


def is_child(doctype: Any) -> bool:
    return getattr(getattr(doctype, "doc", doctype), "is_child", False) is True


async def parent_doctypes(child_name: str) -> list[Any]:
    """Metas of the DocTypes whose Table fields hold *child_name* rows."""
    import grunt
    from grunt.metadata.registry import doctype_registry

    names = {
        dt.name
        for dt in await doctype_registry.list_all()
        if not dt.is_child
        and any(f.fieldtype == "Table" and f.options == child_name for f in dt.fields)
    }
    metas = [await grunt.get_meta(name) for name in sorted(names)]
    return [m for m in metas if m is not None]


async def child_allowed(
    user: User, doctype: Any, action: PermissionAction, doc: dict | None
) -> bool:
    import grunt
    from grunt.permissions.rbac import permission_checker

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


async def child_conditions(table: Table, user: User, doctype: Any) -> ColumnElement[bool]:
    """Rows whose parent document *user* may read, for list queries."""
    from grunt.permissions.reference import readable_names

    if "parent_doctype" not in table.c or "parent_name" not in table.c:
        return false()
    readable: list[ColumnElement[bool]] = []
    for parent_meta in await parent_doctypes(doctype.name):
        names = await readable_names(user, parent_meta)
        if names is not None:
            readable.append(
                and_(table.c.parent_doctype == parent_meta.name, table.c.parent_name.in_(names))
            )
    return or_(*readable) if readable else false()
