""":mod:`grunt.query.nodes` against a row held in memory (a ``dict``).

The same answers as :mod:`grunt.query.compile_sql` (``tests/contract``): values
compared in one type, NULL never matching a comparison, LIKE patterns with
``%`` and ``_``, text case ignored.
"""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
from grunt.query.parse import is_truthy


def is_empty(raw: Any) -> bool:
    return raw in (None, "")


def iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _pair(raw: Any, val: Any) -> tuple[Any, Any] | None:
    """*raw* and *val* in one comparable type; ``None`` when *raw* is NULL (SQL:
    a comparison with NULL is never true) or they can't be compared."""
    if raw is None:
        return None
    if isinstance(raw, bool):  # before int: a bool is an int
        return raw, is_truthy(val)
    if isinstance(raw, (int, float, Decimal)):
        try:
            return float(raw), float(val)
        except TypeError, ValueError:
            return None
    if isinstance(raw, (date, datetime)) or isinstance(val, (date, datetime)):
        return str(iso(raw)), str(iso(val))
    return str(raw), str(val)


def wildcard_match(text: str, pattern: str) -> bool:
    """Whole *text* against a LIKE *pattern* (``%`` any run, ``_`` one character).

    Linear backtracking - only to the last ``%`` - so ``%a%a%a…`` on a long
    row costs O(len(text) * len(pattern)), not the exponential time a regex
    of ``.*`` groups can take (a filter value is user input).
    """
    t = p = 0
    star_p = star_t = -1
    while t < len(text):
        if p < len(pattern) and pattern[p] == "%":
            star_p, star_t = p, t
            p += 1
        elif p < len(pattern) and (pattern[p] == "_" or pattern[p] == text[t]):
            t += 1
            p += 1
        elif star_p >= 0:
            star_t += 1
            t, p = star_t, star_p + 1
        else:
            return False
    return all(ch == "%" for ch in pattern[p:])


def _like(raw: Any, pattern: str) -> bool:
    if raw is None:
        return False
    return wildcard_match(str(iso(raw)).lower(), pattern.lower())


_CMP: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


def _compare(op: str, raw: Any, val: Any) -> bool:
    pair = _pair(raw, val)
    if pair is None:
        return False
    try:
        return _CMP[op](*pair)
    except TypeError:
        return False


def _in(raw: Any, values: tuple[Any, ...]) -> bool:
    return any(_compare("eq", raw, v) for v in values)


def matches(expr: Expr, row: dict[str, Any]) -> bool:
    """Whether *row* satisfies *expr*. A field missing from the row is NULL."""
    match expr:
        case Const(value=value):
            return value
        case And(items=items):
            return all(matches(i, row) for i in items)
        case Or(items=items):
            return any(matches(i, row) for i in items)
        case MultiLink():
            raise NotImplementedError("MultiLink filters need the multi-link table")
        case Linked():
            raise NotImplementedError("Linked filters read another DocType")
        case Raw():
            raise NotImplementedError("A raw SQL condition can't be evaluated in memory")

    raw = row.get(expr.field)
    match expr:
        case Cmp(op=op, value=value):
            return _compare(op, raw, value)
        case Like(pattern=pattern, negate=negate):
            return (raw is None or not _like(raw, pattern)) if negate else _like(raw, pattern)
        case In(values=values, negate=negate):
            if negate:
                return raw is not None and not _in(raw, values)
            return _in(raw, values)
        case Null(negate=negate):
            return (raw is not None) if negate else (raw is None)
        case Empty(negate=negate):
            return not is_empty(raw) if negate else is_empty(raw)
        case Year(year=year):
            return not is_empty(raw) and str(iso(raw))[:4] == f"{year:04d}"
    raise TypeError(f"Not a query node: {expr!r}")


def _reads_db(expr: Expr) -> bool:
    if isinstance(expr, Linked):
        return True
    if isinstance(expr, (And, Or)):
        return any(_reads_db(i) for i in expr.items)
    return False


async def matches_linked(
    expr: Expr, row: dict[str, Any], linked: Callable[[Linked, Any], Awaitable[bool]]
) -> bool:
    """:func:`matches` for an expression with ``Linked`` nodes: *linked* answers
    whether the target DocType holds a row whose ``select`` column is the value
    and that satisfies ``where`` (the caller runs it as a query, compiled like
    the SQL ``IN (subquery)``). In-memory branches are tried before ones that
    read the database, so a role rule that already decides costs no query.

    NULL is in neither ``Linked`` nor its negation, as in SQL.
    """
    match expr:
        case And(items=items):
            for item in sorted(items, key=_reads_db):
                if not await matches_linked(item, row, linked):
                    return False
            return True
        case Or(items=items):
            for item in sorted(items, key=_reads_db):
                if await matches_linked(item, row, linked):
                    return True
            return False
        case Linked(field=field, negate=negate):
            value = row.get(field)
            if value is None:
                return False
            found = await linked(expr, value)
            return not found if negate else found
    return matches(expr, row)
