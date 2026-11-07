""":mod:`grunt.query.nodes` against a row held in memory (a ``dict``).

The same answers as :mod:`grunt.query.compile_sql` (``tests/contract``): values
compared in one type, NULL never matching a comparison, LIKE patterns with
``%`` and ``_``, text case ignored.
"""

from collections.abc import Callable
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
    MultiLink,
    Null,
    Or,
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
