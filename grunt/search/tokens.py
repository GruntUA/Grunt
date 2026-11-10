"""What a user typed into a search box, as terms - and as each full-text engine's query.

Pure string functions with no dependencies: :mod:`grunt.search.terms` (LIKE
search) and :mod:`grunt.db.dialects.fulltext` (native full-text indexes) both
build on them, so every search box splits a query the same way.

The renderers keep only word characters, so a query can never inject
operators into the engine's query language.
"""

import re

#: Hard cap on terms in one query - keeps a pasted paragraph from
#: becoming a 200-way AND of LIKE scans.
MAX_TERMS = 8

_WORD_RE = re.compile(r"[^\W_]+")


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
