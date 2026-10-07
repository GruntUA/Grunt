"""Inherited read access - rows *about* another document (comments, tags,
attachments, files in a folder) are readable by whoever can read that document.

A DocType opts in with ``inherit_permission_from``: a list of sources, each
either a ``[<doctype field>, <id field>]`` pair (comments, attachments) or the
name of a Link field (a file's ``folder``). A row that points at something via
any source is readable when *one* of the documents it points at is - the role's
``match`` doesn't apply to it, though the role still needs a read rule at all.
Rows that point at nothing keep plain role-based access, and so do rows whose
DocType no longer exists; rows whose document was deleted are hidden (as they
are from lists).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, false, or_, select

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, Table

    from grunt.auth.doctypes.User.user import User

# (doctype field, id field) for a dynamic reference; (None, link field) for a Link.
Source = tuple[str | None, str]


def reference_sources(doctype: Any) -> list[Source]:
    raw = getattr(getattr(doctype, "doc", doctype), "inherit_permission_from", None) or []
    sources: list[Source] = []
    for item in raw:
        if isinstance(item, str):
            sources.append((None, item))
        elif len(item) == 2:
            sources.append((item[0], item[1]))
    return sources


def _link_target(doctype: Any, fieldname: str) -> str | None:
    meta = getattr(doctype, "doc", doctype)
    field = next((f for f in meta.fields if f.fieldname == fieldname), None)
    return field.options if field is not None and field.fieldtype == "Link" else None


async def reference_readable(user: User, doctype: Any, doc: dict[str, Any]) -> bool | None:
    """Whether *user* can read one of the documents *doc* points at.

    ``None`` when *doc* points at nothing (or only at a removed DocType): the
    role's own rules decide then (see module doc).
    """
    import grunt
    from grunt.permissions.rbac import permission_checker

    bound = False
    for dt_field, id_field in reference_sources(doctype):
        ref_id = doc.get(id_field)
        ref_doctype = doc.get(dt_field) if dt_field else _link_target(doctype, id_field)
        if not ref_id or not ref_doctype:
            continue
        parent_meta = await grunt.get_meta(ref_doctype)
        if parent_meta is None:
            continue
        bound = True
        lookup = parent_meta.name if parent_meta.is_singleton else ref_id
        parent = await grunt.db.get_value(ref_doctype, lookup, "*")
        if parent is not None and await permission_checker.check(user, parent_meta, "read", parent):
            return True
    return False if bound else None


async def readable_names(user: User, parent_meta: Any) -> Any | None:
    """``SELECT name`` of the *parent_meta* rows *user* may read, or ``None``."""
    from grunt.permissions.query import apply_permission_filter
    from grunt.permissions.rbac import permission_checker
    from grunt.permissions.user_permissions import build_conditions

    if not await permission_checker.check(user, parent_meta, "read"):
        return None
    parent = parent_meta.table
    readable = await apply_permission_filter(select(parent.c.name), parent, user, parent_meta)
    up_conds = await build_conditions(parent, user, parent_meta)
    if up_conds:
        readable = readable.where(and_(*up_conds))
    return readable


async def reference_conditions(
    table: Table, user: User, doctype: Any
) -> tuple[ColumnElement[bool], ColumnElement[bool]] | None:
    """``(points at nothing, points at a readable document)`` for list queries,
    or ``None`` when *doctype* doesn't inherit access."""
    import grunt

    sources = [
        (dt_field, id_field)
        for dt_field, id_field in reference_sources(doctype)
        if id_field in table.c and (dt_field is None or dt_field in table.c)
    ]
    if not sources:
        return None

    unbound: list[ColumnElement[bool]] = []
    readable: list[ColumnElement[bool]] = []
    for dt_field, id_field in sources:
        id_col = table.c[id_field]
        if dt_field is None:
            unbound.append(or_(id_col.is_(None), id_col == ""))
            target = _link_target(doctype, id_field)
            parent_meta = await grunt.get_meta(target) if target else None
            if parent_meta is not None:
                names = await readable_names(user, parent_meta)
                if names is not None:
                    readable.append(id_col.in_(names))
            continue

        dt_col = table.c[dt_field]
        empty = [dt_col.is_(None), dt_col == "", id_col.is_(None), id_col == ""]
        referenced = (await grunt.get_session().execute(select(dt_col).distinct())).scalars().all()
        for ref_doctype in referenced:
            if not ref_doctype:
                continue
            parent_meta = await grunt.get_meta(ref_doctype)
            if parent_meta is None:
                empty.append(dt_col == ref_doctype)  # orphans of a removed DocType
                continue
            names = await readable_names(user, parent_meta)
            if names is not None:
                readable.append(and_(dt_col == ref_doctype, id_col.in_(names)))
        unbound.append(or_(*empty))

    return and_(*unbound), or_(*readable) if readable else false()
