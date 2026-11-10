"""Shared search-query helpers: one way to turn what a user typed into SQL.

Every search box in Grunt (list view, Link dropdown, tree view, virtual
DocTypes, global search) goes through these helpers, so they all behave
the same:

* the query is split into whitespace-separated *terms*;
* a row matches when **every** term is found in **some** searched column
  (``Іван Петренко`` finds a row whose first and last name live in two
  different fields, in any order);
* matching is a case-insensitive substring match with ``%`` / ``_``
  escaped, so a user typing ``50%`` or ``snake_case`` gets what they typed.

Splitting the query into terms, and rendering them for the full-text
engines, lives in the leaf module :mod:`grunt.search.tokens` - the dialect
layer uses it, and this module sits above the dialect layer.
"""

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from grunt.db.dialects import dialect_for
from grunt.db.dialects.base import LIKE_ESCAPE, escape_like  # noqa: F401 - re-exported
from grunt.search.tokens import split_terms


def like_term(col: Any, term: str, dialect: Any) -> ColumnElement:
    """Case-insensitive ``col`` contains ``term`` condition (``Dialect.like_contains``).

    *dialect* - anything :func:`~grunt.db.dialects.dialect_for` accepts
    (a session, engine, backend name or the dialect itself).
    """
    return dialect_for(dialect).like_contains(col, term)


def match_terms(
    query: str | None,
    term_condition: Callable[[str], ColumnElement | None],
) -> ColumnElement | None:
    """AND together ``term_condition(term)`` for every term of *query*.

    Returns ``None`` when the query has no terms (the caller then applies
    no search at all).
    """
    conditions = [c for c in (term_condition(t) for t in split_terms(query)) if c is not None]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else and_(*conditions)


def match_columns(
    query: str | None,
    columns: Iterable[Any],
    dialect: Any,
) -> ColumnElement | None:
    """Every term of *query* must be found in at least one of *columns*."""
    cols = list(columns)
    if not cols:
        return None
    return match_terms(query, lambda term: or_(*(like_term(c, term, dialect) for c in cols)))


def matches_text(query: str | None, values: Iterable[Any]) -> bool:
    """Python counterpart of :func:`match_columns` for in-memory rows."""
    haystack = [str(v).casefold() for v in values if v is not None and v != ""]
    return all(any(t.casefold() in h for h in haystack) for t in split_terms(query))
