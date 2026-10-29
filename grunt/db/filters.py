"""Operator-aware filter dicts -> SQLAlchemy WHERE clauses.

``{"status": "Open", "amount__gte": 10, "title__is": "set"}`` - a key is a
column name plus an optional ``__<op>`` suffix (see ``FILTER_OPS``); all
conditions are ANDed. Shared by ``grunt.db`` and document list queries.

Given the DocType's ``meta``, a MultiLink field (no column of its own - its
values live in ``grunt_core_multi_link``) filters too: ``tags=a`` / ``tags__in``
match documents linking any of the values, ``__ne`` / ``__nin`` those linking
none of them, ``__is`` / ``__isnull`` - having any link at all.
"""

import operator
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, String, and_, cast, exists, false, or_

from grunt.db.types import UtcDateTime
lazy from grunt.metadata.compiler import MULTI_LINK_TABLE

# Operators a filter key may end with (``field__<op>``; no suffix = ``eq``).
# Shared with in-memory filtering of virtual DocTypes (grunt.document.in_memory).
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


def _as_text(col: Any) -> Any:
    """LIKE needs a string column - a number or date is matched by its text."""
    return col if isinstance(col.type, String) else cast(col, String)


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
    "like": lambda col, v: _as_text(col).like(f"%{v}%"),
    "ilike": lambda col, v: _as_text(col).ilike(f"%{v}%"),
    "nlike": lambda col, v: or_(col.is_(None), ~_as_text(col).ilike(f"%{v}%")),
    "in": lambda col, v: col.in_(as_list(v)),
    "nin": lambda col, v: col.not_in(as_list(v)),
    "isnull": lambda col, v: col.is_(None) if is_truthy(v) else col.isnot(None),
    "is": _is_set_clause,
    "year": _year_clause,
}


def _multilink_clause(doctype: str, table: Any, fieldname: str, op: str, value: Any) -> Any:
    """``EXISTS`` over the junction rows of one MultiLink field; ``None`` - op unsupported."""
    ml = MULTI_LINK_TABLE

    def linked(values: list[Any] | None = None) -> Any:
        conds = [
            ml.c.parent_doctype == doctype,
            ml.c.parent_field == fieldname,
            ml.c.parent_name == table.c.name,
        ]
        if values is not None:
            conds.append(ml.c.link_name.in_([str(v) for v in values]))
        return exists().where(*conds)

    if op in ("eq", "in"):
        return linked(as_list(value) if op == "in" else [value])
    if op in ("ne", "neq", "nin"):
        return ~linked(as_list(value) if op == "nin" else [value])
    if op == "isnull":
        return ~linked() if is_truthy(value) else linked()
    if op == "is":
        return ~linked() if str(value).strip().lower() == "not set" else linked()
    return None


def build_clauses(table: Any, filters: dict[str, Any], meta: Any = None) -> list[Any]:
    """WHERE clauses for a filter dict. Unknown columns are skipped.

    ``meta`` (the DocType's :class:`~grunt.document.meta.Meta`) enables
    MultiLink filters - without it they are skipped like unknown columns.
    Virtual DocTypes filter in memory with the same syntax, see
    ``grunt.document.in_memory.apply_filters``.
    """
    multilinks = {f.fieldname for f in meta.get_multilink_fields()} if meta is not None else set()
    clauses: list[Any] = []
    for key, value in filters.items():
        fieldname, op = split_key(key)
        col = table.c.get(fieldname)
        if col is None:
            if fieldname in multilinks:
                clause = _multilink_clause(meta.name, table, fieldname, op, value)
                if clause is not None:
                    clauses.append(clause)
            continue
        if op in _COMPARISONS:
            value = _coerce_for_column(col, value)
        clauses.append(_CLAUSES[op](col, value))
    return clauses


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
