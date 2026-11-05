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

For the full-text index (:mod:`grunt.search.service`) the same terms are
rendered into the dialect's native syntax: SQLite FTS5, PostgreSQL
``tsquery`` or MySQL boolean mode. Those renderers keep only word
characters, so a query can never inject operators into the engine's
query language.
"""

import re
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

lazy import grunt

#: Hard cap on terms in one query - keeps a pasted paragraph from
#: becoming a 200-way AND of LIKE scans.
MAX_TERMS = 8

_WORD_RE = re.compile(r"[^\W_]+")
_LIKE_ESCAPE = "\\"


def split_terms(query: str | None) -> list[str]:
    """Split *query* into unique (case-insensitive) whitespace-separated terms."""
    terms: list[str] = []
    seen: set[str] = set()
    for term in str(query or "").split():
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            terms.append(term)
    return terms[:MAX_TERMS]


def word_parts(term: str) -> list[str]:
    """Return the word-character runs of *term* (``UA-01`` → ``["UA", "01"]``)."""
    return _WORD_RE.findall(term)


def escape_like(term: str) -> str:
    """Escape LIKE wildcards so *term* matches literally."""
    return (
        term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def like_term(col: Any, term: str, dialect: str | None = None) -> ColumnElement:
    """Case-insensitive ``col`` contains ``term`` condition.

    On SQLite ``ILIKE`` compiles to ``lower(col) LIKE lower(?)`` and Grunt
    overrides ``lower()`` with a Python function (SQLite's own is ASCII-only),
    which costs a Python call per row. For an ASCII-only term the native
    ``LIKE`` is already case-insensitive *and* correct - a non-ASCII
    character in the column can never equal an ASCII pattern character - so
    the common searches for codes, numbers and e-mails stay in C.
    """
    pattern = f"%{escape_like(term)}%"
    if dialect == "sqlite" and term.isascii():
        return col.like(pattern, escape=_LIKE_ESCAPE)
    return col.ilike(pattern, escape=_LIKE_ESCAPE)


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
    dialect: str | None = None,
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


def session_dialect(session: Any) -> str | None:
    """Best-effort dialect name of a session/engine/connection (``None`` if unknown)."""
    dialect = getattr(session, "dialect", None)
    if dialect is None:
        bind = getattr(session, "bind", None)
        dialect = getattr(bind, "dialect", None)
    return getattr(dialect, "name", None)


def current_dialect() -> str | None:
    """Dialect of the active request session, or ``None`` outside of one."""
    try:
        return session_dialect(grunt.get_session())
    except Exception:
        return None


# ── Full-text engine query renderers ────────────────────────────────────────


def fts5_query(query: str | None) -> str | None:
    """Render *query* as an SQLite FTS5 MATCH expression.

    Each term becomes a prefix phrase: ``UA-01`` → ``"UA 01"*`` (the
    unicode61 tokenizer splits on the same punctuation, so the phrase
    lines the parts up again). Terms are ANDed implicitly. Only word
    characters reach the expression - no quotes, no operators.
    """
    phrases = []
    for term in split_terms(query):
        parts = word_parts(term)
        if parts:
            phrases.append('"' + " ".join(parts) + '"*')
    return " ".join(phrases) or None


def tsquery(query: str | None) -> str | None:
    """Render *query* for PostgreSQL ``to_tsquery('simple', …)``.

    ``петр іван`` → ``петр:* & іван:*``; a multi-part term becomes a
    phrase (``UA-01`` → ``(ua <-> 01:*)``).
    """
    groups = []
    for term in split_terms(query):
        parts = [p.lower() for p in word_parts(term)]
        if not parts:
            continue
        parts[-1] += ":*"
        groups.append(parts[0] if len(parts) == 1 else "(" + " <-> ".join(parts) + ")")
    return " & ".join(groups) or None


def mysql_boolean_query(query: str | None) -> str | None:
    """Render *query* for MySQL ``MATCH … AGAINST (… IN BOOLEAN MODE)``.

    ``петр іван`` → ``+петр* +іван*``; a multi-part term becomes a quoted
    phrase (``+"ua 01"``) since MySQL has no prefix operator inside phrases.
    """
    groups = []
    for term in split_terms(query):
        parts = word_parts(term)
        if not parts:
            continue
        groups.append(f"+{parts[0]}*" if len(parts) == 1 else '+"' + " ".join(parts) + '"')
    return " ".join(groups) or None
