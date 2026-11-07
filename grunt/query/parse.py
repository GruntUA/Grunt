"""Filter dicts -> :mod:`grunt.query.nodes`.

``{"status": "Open", "amount__gte": 10, "title__is": "set"}`` - a key is a
field name plus an optional ``__<op>`` suffix (see ``FILTER_OPS``); all
conditions are ANDed. A bare string filter means ``name == <string>``.

Given *multilinks* (the DocType's MultiLink fields - no column of their own),
``tags=a`` / ``tags__in`` match documents linking any of the values, ``__ne`` /
``__nin`` those linking none of them, ``__is`` / ``__isnull`` - having any link.
"""

from collections.abc import Collection
from typing import Any

from grunt.query.nodes import (
    FALSE,
    Cmp,
    Empty,
    Expr,
    In,
    Like,
    MultiLink,
    Null,
    Year,
    and_,
    or_,
)

# Operators a filter key may end with (``field__<op>``; no suffix = ``eq``).
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


def _not_set(value: Any) -> bool:
    return str(value).strip().lower() == "not set"


def _year(field: str, value: Any) -> Expr:
    """A value that is not a year matches nothing instead of dropping the filter."""
    try:
        year = int(str(value).strip())
    except ValueError:
        return FALSE
    return Year(field, year) if 1 <= year < 9999 else FALSE


def _leaf(field: str, op: str, value: Any) -> Expr:
    match op:
        case "eq" | "ne" | "gt" | "gte" | "lt" | "lte":
            return Cmp(field, op, value)
        case "neq":
            return Cmp(field, "ne", value)
        case "lte_or_null":
            return or_(Cmp(field, "lte", value), Null(field))
        # like ignores case like ilike - as SQLite always did
        case "like" | "ilike":
            return Like(field, f"%{value}%")
        case "nlike":
            return Like(field, f"%{value}%", negate=True)
        case "in" | "nin":
            return In(field, tuple(as_list(value)), negate=op == "nin")
        case "isnull":
            return Null(field, negate=not is_truthy(value))
        case "is":
            return Empty(field, negate=not _not_set(value))
        case "year":
            return _year(field, value)
    raise NotImplementedError(f"Filter operator {op!r} not supported")


def _multilink(field: str, op: str, value: Any) -> Expr | None:
    """``None`` - an operator a MultiLink field doesn't support (skipped)."""
    match op:
        case "eq" | "in":
            values = as_list(value) if op == "in" else [value]
            return MultiLink(field, tuple(str(v) for v in values))
        case "ne" | "neq" | "nin":
            values = as_list(value) if op == "nin" else [value]
            return MultiLink(field, tuple(str(v) for v in values), negate=True)
        case "isnull":
            return MultiLink(field, None, negate=is_truthy(value))
        case "is":
            return MultiLink(field, None, negate=_not_set(value))
    return None


def parse_filters(
    filters: str | dict[str, Any] | None,
    *,
    fields: Collection[str] | None = None,
    multilinks: Collection[str] = (),
) -> Expr:
    """The filters as one expression (``TRUE`` for none).

    *fields* - the fields that exist; a filter on any other is skipped (a SQL
    table: its columns). ``None`` - every field exists (rows in memory), and a
    key with an operator nobody knows (``dept__child_of``) raises instead of
    quietly matching the wrong rows.
    """
    if isinstance(filters, str):
        return Cmp("name", "eq", filters)
    items: list[Expr] = []
    for key, value in (filters or {}).items():
        field, op = split_key(key)
        if field in multilinks:
            if (node := _multilink(field, op, value)) is not None:
                items.append(node)
            continue
        if fields is None:
            if "__" in field:
                raise ValueError(f"Unsupported filter operator in {key!r}")
        elif field not in fields:
            continue
        items.append(_leaf(field, op, value))
    return and_(*items)
