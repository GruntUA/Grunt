"""Query AST - what rows a query wants, independent of where they are stored.

Nodes name DocType fields, never columns, and hold values as the caller gave
them: typing a value (``"5"`` against a number) is the backend's job - a SQL
column knows its type, an in-memory row knows its value's. Two backends read
the tree: :mod:`grunt.query.compile_sql` (SQLAlchemy) and
:mod:`grunt.query.evaluate` (a ``dict`` row); ``tests/contract`` holds them to
the same answers.

NULL never satisfies a comparison (``Cmp``, ``In``, ``Like``), as in SQL; the
nodes that do match empty values say so (``Null``, ``Empty``, a negated
``Like``). There is no general ``Not`` - SQL's three-valued NOT and Python's
``not`` disagree on NULL, so negation lives in the leaves, each with its NULL
rule spelled out.
"""

from dataclasses import dataclass
from typing import Any, Literal

CmpOp = Literal["eq", "ne", "gt", "gte", "lt", "lte"]


@dataclass(frozen=True, slots=True)
class Cmp:
    """``field <op> value``; NULL matches nothing, ``ne`` included."""

    field: str
    op: CmpOp
    value: Any


@dataclass(frozen=True, slots=True)
class Like:
    """*pattern* (``%`` any run, ``_`` one character) against the field as text,
    case ignored. ``negate`` - not matching, and NULL counts as not matching."""

    field: str
    pattern: str
    negate: bool = False


@dataclass(frozen=True, slots=True)
class In:
    """The field is one of *values* (``negate`` - none of them); NULL is neither."""

    field: str
    values: tuple[Any, ...]
    negate: bool = False


@dataclass(frozen=True, slots=True)
class Null:
    """The field is NULL (``negate`` - is not)."""

    field: str
    negate: bool = False


@dataclass(frozen=True, slots=True)
class Empty:
    """The field is NULL or ``''`` (``negate`` - has a value) - a cleared text
    field may be stored either way."""

    field: str
    negate: bool = False


@dataclass(frozen=True, slots=True)
class Year:
    """A date/datetime within calendar *year* (a half-open range in SQL, so an
    index on the field still applies)."""

    field: str
    year: int


@dataclass(frozen=True, slots=True)
class MultiLink:
    """A MultiLink field links any of *values* - ``None``: links anything at all;
    ``negate`` - links none of them (nothing at all)."""

    field: str
    values: tuple[str, ...] | None
    negate: bool = False


@dataclass(frozen=True, slots=True)
class And:
    items: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class Or:
    items: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class Const:
    """Every row (``True``) or none (``False``)."""

    value: bool


TRUE = Const(True)
FALSE = Const(False)

type Leaf = Cmp | Like | In | Null | Empty | Year | MultiLink
type Expr = Leaf | And | Or | Const


def and_(*items: Expr) -> Expr:
    """AND, flattened: ``TRUE`` drops out, ``FALSE`` wins, one item is itself."""
    flat: list[Expr] = []
    for item in items:
        if item == FALSE:
            return FALSE
        if item == TRUE:
            continue
        flat.extend(item.items if isinstance(item, And) else (item,))
    if not flat:
        return TRUE
    return flat[0] if len(flat) == 1 else And(tuple(flat))


def or_(*items: Expr) -> Expr:
    """OR, flattened: ``FALSE`` drops out, ``TRUE`` wins, one item is itself."""
    flat: list[Expr] = []
    for item in items:
        if item == TRUE:
            return TRUE
        if item == FALSE:
            continue
        flat.extend(item.items if isinstance(item, Or) else (item,))
    if not flat:
        return FALSE
    return flat[0] if len(flat) == 1 else Or(tuple(flat))


def conjuncts(expr: Expr) -> tuple[Expr, ...]:
    """The items an expression ANDs together (itself, when it isn't an AND)."""
    if isinstance(expr, And):
        return expr.items
    return () if expr == TRUE else (expr,)


__all__ = [
    "FALSE",
    "TRUE",
    "And",
    "Cmp",
    "CmpOp",
    "Const",
    "Empty",
    "Expr",
    "In",
    "Leaf",
    "Like",
    "MultiLink",
    "Null",
    "Or",
    "Year",
    "and_",
    "conjuncts",
    "or_",
]
