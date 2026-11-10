"""What a report can read: its DocType's fields, and fields through a Link.

``customer.region`` - the ``region`` of the document the ``customer`` Link
points at - becomes a ``LEFT JOIN`` of that DocType's table with the target's
row-level rules (``read_predicate``) in the ``ON`` clause. A report row stays
when its target is unreadable (or the Link is empty); the target's fields are
then empty, so filtering or grouping by them gives nothing about rows the
viewer may not read.

A field the viewer may not see - hidden by field-level permissions, or on a
DocType they can't read at all - is not part of the source: a column is left
out, a filter or condition on it is skipped, like any unknown column.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Table, and_
from sqlalchemy.sql import FromClause
from sqlalchemy.sql.base import WriteableColumnCollection

from grunt.metadata.registry import doctype_registry
from grunt.permissions.query import read_predicate
from grunt.permissions.rbac import permission_checker
from grunt.query.nodes import TRUE
from grunt.query.sql import where_clause
lazy from grunt.api.v1.meta import _dump_doctype


@dataclass
class ReportSource:
    """``c`` - the readable columns by report fieldname (``status``,
    ``customer.region``); ``from_`` - the table with its joins."""

    table: Table
    c: WriteableColumnCollection
    from_: FromClause
    joined: frozenset[str]


def _link_target(meta: Any, fieldname: str) -> str | None:
    field = next((f for f in meta.fields if f.fieldname == fieldname), None)
    if field is None or not field.has_trait("link") or not field.options:
        return None
    return field.options


async def report_source(meta: Any, user: str, fieldnames: Iterable[str]) -> ReportSource:
    """The source for a report on *meta* reading *fieldnames* (dotted ones
    join their Link's DocType - one join per Link, whatever fields it gives)."""
    table = meta.table
    hidden = await permission_checker.hidden_fields(meta, user=user)
    columns = WriteableColumnCollection()
    for col in table.c:
        if col.key not in hidden:
            columns.add(col)

    wanted: dict[str, set[str]] = {}
    for name in fieldnames:
        link, sep, field = name.partition(".")
        if sep and field and "." not in field:
            wanted.setdefault(link, set()).add(field)

    from_: FromClause = table
    joined: set[str] = set()
    for link in sorted(wanted):
        if link not in columns or (target_name := _link_target(meta, link)) is None:
            continue
        target = await doctype_registry.get_meta(target_name)
        if target is None or not await permission_checker.check(target, "read", user=user):
            continue
        target_hidden = await permission_checker.hidden_fields(target, user=user)
        alias = target.table.alias(f"j_{link}")
        readable = await read_predicate(user, target)
        on = table.c[link] == alias.c.name
        if readable != TRUE:
            on = and_(on, await where_clause(readable, alias, target.name))
        from_ = from_.outerjoin(alias, on)
        for field in sorted(wanted[link]):
            if field in alias.c and field not in target_hidden:
                columns.add(alias.c[field], key=f"{link}.{field}")
                joined.add(f"{link}.{field}")
    return ReportSource(table, columns, from_, frozenset(joined))


async def report_fields(meta: Any, user: str) -> list[dict[str, Any]]:
    """The fields a report on *meta* can read for *user* - what the builder
    offers: the DocType's own (without hidden ones) and, through each Link, the
    stored fields of a target *user* may read (``customer.region``, labelled
    ``Клієнт → Регіон``). The same rules as :func:`report_source`, so nothing
    offered is silently left out of the report."""
    hidden = await permission_checker.hidden_fields(meta, user=user)
    own = [
        f
        for f in (await _dump_doctype(meta.doc, translate=True))["fields"]
        if f["fieldname"] not in hidden
    ]
    fields = list(own)
    for link in own:
        name = link["fieldname"]
        if name not in meta.columns or (target_name := _link_target(meta, name)) is None:
            continue
        target = await doctype_registry.get_meta(target_name)
        if target is None or not await permission_checker.check(target, "read", user=user):
            continue
        target_hidden = await permission_checker.hidden_fields(target, user=user)
        for f in (await _dump_doctype(target.doc, translate=True))["fields"]:
            if f["fieldname"] in target.columns and f["fieldname"] not in target_hidden:
                fields.append(
                    {
                        **f,
                        "fieldname": f"{name}.{f['fieldname']}",
                        "label": f"{link['label']} → {f['label']}",
                    }
                )
    return fields
