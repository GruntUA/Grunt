"""Operator-aware filter dicts -> SQLAlchemy WHERE clauses.

``{"status": "Open", "amount__gte": 10, "title__is": "set"}`` - a key is a
column name plus an optional ``__<op>`` suffix (see ``FILTER_OPS``); all
conditions are ANDed. Shared by ``grunt.db`` and document list queries.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, String, and_, false, or_

from grunt.db.types import UtcDateTime

if TYPE_CHECKING:
    from collections.abc import Callable

# Operators a filter key may end with (``field__<op>``; no suffix = ``eq``).
# Shared with in-memory filtering of virtual DocTypes (grunt.metadata.virtual).
# Ordered longest-first so multi-word suffixes (``__lte_or_null``) win over
# their prefixes.
FILTER_OPS = (
    "lte_or_null",
    "isnull",
    "nlike",
    "like",
    "ilike",
    "gte",
    "lte",
    "nin",
    "neq",
    "year",
    "gt",
    "lt",
    "eq",
    "in",
    "ne",
    "is",
)


def split_key(key: str) -> tuple[str, str]:
    """``"amount__gte"`` -> ``("amount", "gte")``; no known suffix -> ``(key, "eq")``.

    Only known operators are split off, so a field literally named ``foo__bar``
    stays whole instead of being misread as ``foo`` + op ``bar``.
    """
    for op in FILTER_OPS:
        if key.endswith(f"__{op}"):
            return key[: -len(op) - 2], op
    return key, "eq"


def is_truthy(value: Any) -> bool:
    """Interpret filter values that may arrive as bools or query strings."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0", "no")
    return bool(value)


def as_list(value: Any) -> list[Any]:
    """Normalise an ``in``/``nin`` operand from either a list or a CSV string
    (``"a, b,"`` -> ``["a", "b"]``)."""
    if isinstance(value, (list, tuple)):
        return list(value)
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _is_set_clause(col: Any, value: Any) -> Any:
    """``field__is=set|not set`` - empty means NULL, and also ``''`` for text columns
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
    (caught by the widget's own try/except, surfacing as an empty chart) -
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


def _year_clause(col: Any, value: Any) -> Any:
    """``field__year=2022`` - a date/datetime within that calendar year.

    Compiled as a half-open range (``>= 2022-01-01 AND < 2023-01-01``) rather
    than ``strftime``/``EXTRACT`` so an index on the column still applies. A
    value that is not a year matches nothing instead of dropping the filter.
    """
    try:
        year = int(str(value).strip())
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    except ValueError, OverflowError:
        return false()
    col_type = getattr(col, "type", None)
    if isinstance(col_type, UtcDateTime):
        lo, hi = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    elif isinstance(col_type, Date):
        lo, hi = start, end
    else:  # ISO text - compares lexically
        lo, hi = start.isoformat(), end.isoformat()
    return and_(col >= lo, col < hi)


# Operators whose value is compared with the column, so ISO date strings
# have to be parsed into date/datetime first.
_COMPARISONS = frozenset({"eq", "ne", "neq", "gt", "gte", "lt", "lte", "lte_or_null"})

_CLAUSES: dict[str, Callable[[Any, Any], Any]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "lte_or_null": lambda col, v: or_(col <= v, col.is_(None)),
    "like": lambda col, v: col.like(f"%{v}%"),
    "ilike": lambda col, v: col.ilike(f"%{v}%"),
    "nlike": lambda col, v: or_(col.is_(None), ~col.ilike(f"%{v}%")),
    "in": lambda col, v: col.in_(as_list(v)),
    "nin": lambda col, v: col.not_in(as_list(v)),
    "isnull": lambda col, v: col.is_(None) if is_truthy(v) else col.isnot(None),
    "is": _is_set_clause,
    "year": _year_clause,
}


def build_clauses(table: Any, filters: dict[str, Any]) -> list[Any]:
    """WHERE clauses for a filter dict. Unknown columns are skipped.

    Virtual DocTypes filter in memory with the same syntax, see
    ``VirtualDocType.apply_filters``.
    """
    clauses: list[Any] = []
    for key, value in filters.items():
        fieldname, op = split_key(key)
        col = table.c.get(fieldname)
        if col is None:
            continue
        if op in _COMPARISONS:
            value = _coerce_for_column(col, value)
        clauses.append(_CLAUSES[op](col, value))
    return clauses


def apply_filters(stmt: Any, table: Any, filters: str | dict[str, Any] | None) -> Any:
    """AND the filters onto ``stmt``: a bare string matches ``name``, a dict goes
    through ``build_clauses``."""
    if isinstance(filters, str):
        return stmt.where(table.c.name == filters)
    for clause in build_clauses(table, filters or {}):
        stmt = stmt.where(clause)
    return stmt
