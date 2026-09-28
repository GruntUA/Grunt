"""Operator-aware filter dicts → SQLAlchemy WHERE clauses.

``{"status": "Open", "amount__gte": 10, "title__is": "set"}`` — a key is a
column name plus an optional ``__<op>`` suffix (see ``_FILTER_OPS``); all
conditions are ANDed. Shared by ``grunt.db`` and document list queries.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, String, or_

from grunt.db.types import UtcDateTime

# Ordered longest-first so multi-word suffixes (``__lte_or_null``) win over
# their prefixes. Anchoring on ``__`` also keeps a field literally named
# ``foo__bar`` (no operator) from being misread as ``foo`` + op ``bar``.
_FILTER_OPS = (
    "__lte_or_null",
    "__isnull",
    "__nlike",
    "__like",
    "__ilike",
    "__gte",
    "__lte",
    "__nin",
    "__neq",
    "__gt",
    "__lt",
    "__eq",
    "__in",
    "__ne",
    "__is",
)


def _truthy(value: Any) -> bool:
    """Interpret filter values that may arrive as bools or query strings."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0", "no")
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    """Normalise an ``in``/``nin`` operand from either a list or a CSV string."""
    return list(value) if isinstance(value, (list, tuple)) else str(value).split(",")


def _is_set_clause(col: Any, value: Any) -> Any:
    """``field__is=set|not set`` — empty means NULL, and also ``''`` for text columns
    (a cleared Data/Text/RichText field may be stored either way)."""
    empty = col.is_(None)
    if isinstance(col.type, String):
        empty = or_(empty, col == "")
    return empty if str(value).strip().lower() == "not set" else ~empty


def _coerce_for_column(col: Any, value: Any) -> Any:
    """Parse an ISO date/datetime string filter value to match its column's type.

    Callers build filter dicts from Python code (dashboard widgets computing
    ``since``/``until`` as ISO strings, query params, JSON) rather than always
    handing over real ``date``/``datetime`` objects. SQLAlchemy's bind
    processors for ``Date``/``UtcDateTime`` only accept the real object and
    raise ``TypeError`` on a bare string, so comparisons silently blow up
    (caught by the widget's own try/except, surfacing as an empty chart) —
    coerce once, here, instead of at every call site.
    """
    if not isinstance(value, str):
        return value
    col_type = getattr(col, "type", None)
    try:
        if isinstance(col_type, UtcDateTime):
            return datetime.fromisoformat(value)
        if isinstance(col_type, Date):
            return date.fromisoformat(value[:10])
    except ValueError:
        return value
    return value


def build_clauses(table: Any, filters: dict[str, Any]) -> list[Any]:
    """Build SQLAlchemy WHERE clauses from an operator-aware filter dict.

    Single source of truth for filter parsing across *physical* DocTypes — used
    both by the ``grunt.db`` layer (count/get_all/…) and by document list
    queries. Virtual DocTypes filtering in-memory rows use the equivalent
    ``VirtualDocType.apply_filters`` (``grunt.metadata.virtual``) instead,
    which intentionally mirrors the same operator set.
    """
    clauses: list[Any] = []
    for key, value in filters.items():
        op = "eq"
        fieldname = key
        for suffix in _FILTER_OPS:
            if key.endswith(suffix):
                fieldname = key[: -len(suffix)]
                op = suffix[2:]
                break

        col = table.c.get(fieldname)
        if col is None:
            continue

        if op in ("eq", "ne", "neq", "gte", "lte", "lte_or_null", "gt", "lt"):
            value = _coerce_for_column(col, value)

        if op == "eq":
            clauses.append(col == value)
        elif op in ("ne", "neq"):
            clauses.append(col != value)
        elif op == "gte":
            clauses.append(col >= value)
        elif op == "lte":
            clauses.append(col <= value)
        elif op == "lte_or_null":
            clauses.append(or_(col <= value, col.is_(None)))
        elif op == "gt":
            clauses.append(col > value)
        elif op == "lt":
            clauses.append(col < value)
        elif op == "like":
            clauses.append(col.like(f"%{value}%"))
        elif op == "ilike":
            clauses.append(col.ilike(f"%{value}%"))
        elif op == "nlike":
            clauses.append(or_(col.is_(None), ~col.ilike(f"%{value}%")))
        elif op == "in":
            clauses.append(col.in_(_as_list(value)))
        elif op == "nin":
            clauses.append(col.not_in(_as_list(value)))
        elif op == "isnull":
            clauses.append(col.is_(None) if _truthy(value) else col.isnot(None))
        elif op == "is":
            clauses.append(_is_set_clause(col, value))
    return clauses


def apply_filters(stmt: Any, table: Any, filters: str | dict[str, Any] | None) -> Any:
    """AND the filters onto ``stmt``: a bare string matches ``name``, a dict goes
    through ``build_clauses``."""
    if isinstance(filters, str):
        return stmt.where(table.c.name == filters)
    for clause in build_clauses(table, filters or {}):
        stmt = stmt.where(clause)
    return stmt
