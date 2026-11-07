"""Query predicates on a SQL statement - the one way filters and row-level
permissions reach a ``WHERE``.

``filter_expr`` turns a filter dict into an expression for a table (unknown
columns skipped, MultiLink fields through the DocType's meta); ``where`` ANDs
an expression onto a statement, loading the table of every DocType a
``Linked`` node reads. Permissions come in as an expression too
(``grunt.permissions.query.read_predicate``) - ANDed like any filter, so there
is no separate step a read path could forget.
"""

from typing import Any

from sqlalchemy import ColumnElement, Table

import grunt
from grunt.query.compile_sql import to_sql
from grunt.query.nodes import TRUE, Expr, linked_doctypes
from grunt.query.parse import parse_filters


def filter_expr(filters: str | dict[str, Any] | None, table: Any, meta: Any = None) -> Expr:
    """*filters* (a dict, or a bare string - the ``name``) as an expression on
    *table*. Unknown columns are skipped; ``meta`` (the DocType's
    :class:`~grunt.document.meta.Meta`) enables MultiLink filters."""
    multilinks = {f.fieldname for f in meta.get_multilink_fields()} if meta is not None else ()
    return parse_filters(filters, fields=table.c.keys(), multilinks=multilinks)


async def linked_tables(expr: Expr) -> dict[str, Table]:
    """The table of every DocType a ``Linked`` node in *expr* reads."""
    tables: dict[str, Table] = {}
    for name in linked_doctypes(expr):
        meta = await grunt.get_meta(name)
        if meta is None:  # a predicate only names DocTypes it just loaded
            raise LookupError(f"DocType {name!r} disappeared while filtering")
        tables[name] = meta.table
    return tables


async def where_clause(expr: Expr, table: Any, doctype: str | None) -> ColumnElement[bool]:
    """*expr* as a WHERE clause on *table* (the rows of *doctype*)."""
    return to_sql(expr, table, doctype=doctype, tables=await linked_tables(expr))


async def where(stmt: Any, expr: Expr, table: Any, doctype: str | None) -> Any:
    """*stmt* with *expr* ANDed onto its WHERE (unchanged for ``TRUE``)."""
    if expr == TRUE:
        return stmt
    return stmt.where(await where_clause(expr, table, doctype))
