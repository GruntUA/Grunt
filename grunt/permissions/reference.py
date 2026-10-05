"""Inherited read access - rows *about* another document (comments, tags,
attachments) are readable only by users who can read that document.

A DocType opts in with ``inherit_permission_from = [<doctype field>, <id field>]``
(e.g. ``["reference_doctype", "reference_id"]``). Role permissions still apply
first; this only narrows them. Rows that point at nothing (a library file) or at
a DocType that no longer exists keep plain role-based access; rows whose
document was deleted are hidden (as they are from lists).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, distinct, or_, select

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.sql import Select

    from grunt.auth.doctypes.User.user import User


def reference_fields(doctype: Any) -> tuple[str, str] | None:
    pair = getattr(getattr(doctype, "doc", doctype), "inherit_permission_from", None)
    return (pair[0], pair[1]) if pair and len(pair) == 2 else None


async def reference_readable(user: User, doctype: Any, doc: dict[str, Any]) -> bool:
    """True if *doc* points at nothing, at a removed DocType, or at a document *user* can read."""
    import grunt
    from grunt.permissions.rbac import permission_checker

    fields = reference_fields(doctype)
    if fields is None:
        return True
    ref_doctype, ref_id = doc.get(fields[0]), doc.get(fields[1])
    if not ref_doctype or not ref_id:
        return True
    parent_meta = await grunt.get_meta(ref_doctype)
    if parent_meta is None:
        return True
    lookup = parent_meta.name if parent_meta.is_singleton else ref_id
    parent = await grunt.db.get_value(ref_doctype, lookup, "*")
    if parent is None:
        return False
    return await permission_checker.check(user, parent_meta, "read", parent)


async def apply_reference_filter(query: Select, table: Table, user: User, doctype: Any) -> Select:
    """Keep only rows whose referenced document *user* may read (see module doc)."""
    import grunt
    from grunt.permissions.query import apply_permission_filter
    from grunt.permissions.rbac import permission_checker
    from grunt.permissions.user_permissions import build_conditions

    fields = reference_fields(doctype)
    if fields is None or fields[0] not in table.c or fields[1] not in table.c:
        return query
    dt_col, id_col = table.c[fields[0]], table.c[fields[1]]

    conditions = [dt_col.is_(None), dt_col == "", id_col.is_(None), id_col == ""]
    referenced = (await grunt.get_session().execute(select(distinct(dt_col)))).scalars().all()
    for ref_doctype in referenced:
        if not ref_doctype:
            continue
        parent_meta = await grunt.get_meta(ref_doctype)
        if parent_meta is None:
            conditions.append(dt_col == ref_doctype)  # orphans of a removed DocType
            continue
        if not await permission_checker.check(user, parent_meta, "read"):
            continue
        parent = parent_meta.table
        readable = await apply_permission_filter(select(parent.c.name), parent, user, parent_meta)
        up_conds = await build_conditions(parent, user, parent_meta)
        if up_conds:
            readable = readable.where(and_(*up_conds))
        conditions.append(and_(dt_col == ref_doctype, id_col.in_(readable)))

    return query.where(or_(*conditions))
