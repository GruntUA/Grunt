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

from typing import Any

from sqlalchemy import Table, select

from grunt.query.nodes import Cmp, Empty, Expr, Linked, and_, or_
lazy import grunt
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.permissions.query import read_predicate
lazy from grunt.permissions.rbac import permission_checker

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
    return field.options if field is not None and field.has_trait("link") else None


async def reference_readable(user: User, doctype: Any, doc: dict[str, Any]) -> bool | None:
    """Whether *user* can read one of the documents *doc* points at.

    ``None`` when *doc* points at nothing (or only at a removed DocType): the
    role's own rules decide then (see module doc).
    """

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


async def readable_predicate(user: User, parent_meta: Any) -> Expr | None:
    """The rows of *parent_meta* that *user* may read, as a predicate on them -
    ``None`` when *user* can't read that DocType at all."""
    if not await permission_checker.check(user, parent_meta, "read"):
        return None
    return await read_predicate(parent_meta.table, user, parent_meta)


async def reference_predicates(table: Table, user: User, doctype: Any) -> tuple[Expr, Expr] | None:
    """``(points at nothing, points at a readable document)`` for list queries,
    or ``None`` when *doctype* doesn't inherit access."""
    sources = [
        (dt_field, id_field)
        for dt_field, id_field in reference_sources(doctype)
        if id_field in table.c and (dt_field is None or dt_field in table.c)
    ]
    if not sources:
        return None
    unbound: list[Expr] = []
    readable: list[Expr] = []
    for dt_field, id_field in sources:
        if dt_field is None:
            unbound.append(Empty(id_field))
            target = _link_target(doctype, id_field)
            parent_meta = await grunt.get_meta(target) if target else None
            if parent_meta is not None:
                where = await readable_predicate(user, parent_meta)
                if where is not None:
                    readable.append(Linked(id_field, parent_meta.name, where))
            continue
        empty: list[Expr] = [Empty(dt_field), Empty(id_field)]
        dt_col = table.c[dt_field]
        referenced = (await grunt.get_session().execute(select(dt_col).distinct())).scalars().all()
        for ref_doctype in referenced:
            if not ref_doctype:
                continue
            parent_meta = await grunt.get_meta(ref_doctype)
            if parent_meta is None:
                empty.append(Cmp(dt_field, "eq", ref_doctype))  # orphans of a removed DocType
                continue
            where = await readable_predicate(user, parent_meta)
            if where is not None:
                readable.append(
                    and_(
                        Cmp(dt_field, "eq", ref_doctype), Linked(id_field, parent_meta.name, where)
                    )
                )
        unbound.append(or_(*empty))
    return and_(*unbound), or_(*readable)
