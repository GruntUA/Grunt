""":mod:`grunt.query.nodes` -> SQLAlchemy, against one table.

Values are typed by the column here (``"5"`` for an Int column is ``5`` - SQLite
compares either way, PostgreSQL refuses ``int = '5'``); the AST keeps them as
given. A relative day (``today``, ``today-30`` - :mod:`grunt.utils.dates`) on a
date column is that day; on a date-and-time column it is the whole local day.
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, String, Table, and_, cast, exists, false, or_, select, true

from grunt.db.types import IsoDate, UtcDateTime
from grunt.query.nodes import (
    And,
    Cmp,
    Const,
    Empty,
    Expr,
    In,
    Like,
    Linked,
    MultiLink,
    Null,
    Or,
    Raw,
    Year,
)
from grunt.utils.dates import local_day_start, relative_date
lazy from grunt.metadata.compiler import MULTI_LINK_TABLE

_NUMBER_TYPES = (int, float, Decimal)


def typed_value(col: Any, value: Any) -> Any:
    """A number typed as a string (a query string, a CSV list) as a number for a
    numeric column, a relative day as a date for a date column (a date-and-time
    one: the day's local midnight). Any other value stays as it is."""
    if not isinstance(value, str):
        return value
    if isinstance(col.type, (IsoDate, UtcDateTime)) and (day := relative_date(value)):
        return local_day_start(day) if isinstance(col.type, UtcDateTime) else day
    try:
        python_type = col.type.python_type
    except NotImplementedError:
        return value
    if python_type not in _NUMBER_TYPES:
        return value
    try:
        return python_type(value.strip())
    except ValueError, ArithmeticError:
        return value


def _as_text(col: Any) -> Any:
    """LIKE needs a string column - a number or date is matched by its text."""
    return col if isinstance(col.type, String) else cast(col, String)


def _empty(col: Any) -> Any:
    """NULL, and also ``''`` for text columns."""
    empty = col.is_(None)
    return or_(empty, col == "") if isinstance(col.type, String) else empty


def _year(col: Any, year: int) -> Any:
    col_type = getattr(col, "type", None)
    if isinstance(col_type, UtcDateTime):
        lo, hi = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    elif isinstance(col_type, IsoDate):
        lo, hi = date(year, 1, 1), date(year + 1, 1, 1)
    else:  # ISO text - compares lexically
        lo, hi = date(year, 1, 1).isoformat(), date(year + 1, 1, 1).isoformat()
    return and_(col >= lo, col < hi)


_CMP = {
    "eq": lambda c, v: c == v,
    "ne": lambda c, v: c != v,
    "gt": lambda c, v: c > v,
    "gte": lambda c, v: c >= v,
    "lt": lambda c, v: c < v,
    "lte": lambda c, v: c <= v,
}


def _relative_day(col: Any, op: str, day: date) -> Any:
    """A comparison with a relative *day* on a date-and-time column, as the whole
    local day: ``= today`` - any moment of today, ``<= today`` - up to its end."""
    lo, hi = local_day_start(day), local_day_start(day + timedelta(days=1))
    match op:
        case "eq":
            return and_(col >= lo, col < hi)
        case "ne":
            return or_(col < lo, col >= hi)
        case "gt":
            return col >= hi
        case "gte":
            return col >= lo
        case "lt":
            return col < lo
    return col < hi  # lte


def to_sql(
    expr: Expr,
    table: Any,
    *,
    doctype: str | None = None,
    tables: Mapping[str, Table] | None = None,
) -> ColumnElement[bool]:
    """*expr* as a WHERE clause on *table*.

    *doctype* - for ``MultiLink`` (its rows in ``grunt_core_multi_link`` are keyed
    by the DocType's name); *tables* - the table of every DocType a ``Linked``
    node reads (:func:`grunt.query.nodes.linked_doctypes`).
    """

    def sub(e: Expr) -> ColumnElement[bool]:
        return to_sql(e, table, doctype=doctype, tables=tables)

    match expr:
        case MultiLink():
            return _multilink(expr, table, doctype)
        case Const(value=value):
            return true() if value else false()
        case And(items=items):
            return and_(*(sub(i) for i in items))
        case Or(items=items):
            return or_(*(sub(i) for i in items))
        case Raw(clause=clause):
            return clause
        case Linked(field=field, doctype=target_doctype, where=where, select=column, negate=negate):
            if tables is None or target_doctype not in tables:
                raise ValueError(
                    f"Linked filter on {field!r} needs the table of {target_doctype!r}"
                )
            target = tables[target_doctype]
            inner = to_sql(where, target, doctype=target_doctype, tables=tables)
            subquery = select(target.c[column]).where(inner)
            col = table.c[field]
            return col.not_in(subquery) if negate else col.in_(subquery)

    col = table.c[expr.field]
    match expr:
        case Cmp(op=op, value=value):
            if isinstance(col.type, UtcDateTime) and (day := relative_date(value)):
                return _relative_day(col, op, day)
            return _CMP[op](col, typed_value(col, value))
        case Like(pattern=pattern, negate=False):
            return _as_text(col).ilike(pattern)
        case Like(pattern=pattern, negate=True):
            return or_(col.is_(None), ~_as_text(col).ilike(pattern))
        case In(values=values, negate=negate):
            typed = [typed_value(col, v) for v in values]
            return col.not_in(typed) if negate else col.in_(typed)
        case Null(negate=negate):
            return col.isnot(None) if negate else col.is_(None)
        case Empty(negate=negate):
            return ~_empty(col) if negate else _empty(col)
        case Year(year=year):
            return _year(col, year)
    raise TypeError(f"Not a query node: {expr!r}")


def _multilink(node: MultiLink, table: Any, doctype: str | None) -> ColumnElement[bool]:
    """``EXISTS`` over the junction rows of one MultiLink field."""
    if doctype is None:
        raise ValueError(f"MultiLink filter on {node.field!r} needs the DocType")
    ml = MULTI_LINK_TABLE
    conds = [
        ml.c.parent_doctype == doctype,
        ml.c.parent_field == node.field,
        ml.c.parent_name == table.c.name,
    ]
    if node.values is not None:
        conds.append(ml.c.link_name.in_(node.values))
    linked = exists().where(*conds)
    return ~linked if node.negate else linked
