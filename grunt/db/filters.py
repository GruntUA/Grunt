"""Filter dicts -> SQLAlchemy WHERE clauses, through the query AST.

``{"status": "Open", "amount__gte": 10, "title__is": "set"}`` - parsed by
:func:`grunt.query.parse.parse_filters`, compiled by
:func:`grunt.query.compile_sql.to_sql`. Unknown columns are skipped. Virtual
DocTypes filter the same AST in memory (``grunt.document.in_memory``).

These wrappers go once every list path builds a ``Query`` (DB_LAYERS_PLAN.md,
step 3c).
"""

from typing import Any

from grunt.query.compile_sql import to_sql, typed_value
from grunt.query.nodes import conjuncts
from grunt.query.parse import FILTER_OPS, as_list, is_truthy, parse_filters, split_key

# Filter-bar ("display") operator -> ``FILTER_OPS`` suffix. The vocabulary of
# report conditions and saved list filters; the frontend twin is FILTER_OPS in
# frontend/src/core/filterOps.ts (tests/unit/test_filter_ops_sync.py).
# ``child_of`` is not a ``build_clauses`` operator: callers expand it to the
# subtree first (grunt.document.query.expand_child_of_filters).
DISPLAY_OPS: dict[str, str] = {
    "=": "eq",
    "!=": "ne",
    ">": "gt",
    "<": "lt",
    ">=": "gte",
    "<=": "lte",
    "like": "ilike",
    "not like": "nlike",
    "in": "in",
    "not in": "nin",
    "is set": "is",
    "is not set": "is",
    "child_of": "child_of",
}


def build_clauses(table: Any, filters: dict[str, Any], meta: Any = None) -> list[Any]:
    """WHERE clauses (to AND) for a filter dict. Unknown columns are skipped.

    ``meta`` (the DocType's :class:`~grunt.document.meta.Meta`) enables
    MultiLink filters - without it they are skipped like unknown columns.
    """
    multilinks = {f.fieldname for f in meta.get_multilink_fields()} if meta is not None else ()
    expr = parse_filters(filters, fields=table.c.keys(), multilinks=multilinks)
    doctype = meta.name if meta is not None else None
    return [to_sql(item, table, doctype=doctype) for item in conjuncts(expr)]


def apply_filters(
    stmt: Any, table: Any, filters: str | dict[str, Any] | None, meta: Any = None
) -> Any:
    """AND the filters onto ``stmt``: a bare string matches ``name``, a dict goes
    through ``build_clauses``."""
    if isinstance(filters, str):
        return stmt.where(table.c.name == filters)
    for clause in build_clauses(table, filters or {}, meta):
        stmt = stmt.where(clause)
    return stmt


__all__ = [
    "DISPLAY_OPS",
    "FILTER_OPS",
    "apply_filters",
    "as_list",
    "build_clauses",
    "is_truthy",
    "split_key",
    "typed_value",
]
