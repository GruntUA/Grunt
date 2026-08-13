"""A single parsed DocTypePermission.match expression.

`match` (e.g. ``"owner == user"``) is evaluated two different ways depending
on where a permission check happens:

- Row-level list/count filtering (``permissions/query.py``) needs it as a
  SQL condition — necessarily a narrow subset (``field == value`` /
  ``field != value`` on a literal or ``user``), since translating arbitrary
  boolean expressions to SQL safely is a much bigger undertaking.
- Per-document checks (``permissions/rbac.py``) need it evaluated in Python
  against an already-fetched row, via ``simpleeval`` — which supports the
  full expression syntax, not just the SQL-translatable subset.

Before this class existed, those two evaluations were two independent
implementations of the same domain concept, and had already drifted apart
once (one failed open, the other silently treated "can't translate" as
"unrestricted" instead of "deny"). Parsing and evaluating the expression in
one place makes that kind of drift structurally harder to reintroduce.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.sql import ColumnElement

    from grunt.auth.doctypes.User.user import User

logger = structlog.get_logger()

# "<field> == <value>" / "<field> != <value>", value is either the bare word
# `user` (→ current user's email) or a single/double-quoted string literal.
_MATCH_RE = re.compile(
    r"^(?P<field>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?P<op>==|!=)\s*(?P<value>.+)$"
)


class PermissionMatch:
    """A parsed ``match`` expression, evaluable as SQL or as Python."""

    def __init__(self, expr: str) -> None:
        self.expr = expr.strip()
        self._parsed = self._parse()

    def _parse(self) -> tuple[str, str, str] | None:
        """Return ``(field, op, raw_value)`` for the narrow SQL-translatable
        form, or None when *expr* isn't in that form (arbitrary boolean
        logic, non-string/non-`user` literals, ...).
        """
        m = _MATCH_RE.match(self.expr)
        if not m:
            return None
        return m.group("field"), m.group("op"), m.group("value").strip()

    def to_sql(self, table: Table, user: User) -> ColumnElement | None:
        """SQL condition for row-level list/count filtering.

        Returns None when this expression can't be translated — the caller
        must treat that as "can't enforce this rule" (deny/skip), never as
        "unrestricted", or an unparseable rule would silently expose every
        row instead of none.
        """
        if self._parsed is None:
            return None
        field, op, raw_value = self._parsed
        if not hasattr(table.c, field):
            return None

        if raw_value == "user":
            value: str = user.email
        elif len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "'\"":
            value = raw_value[1:-1]
        else:
            return None  # numbers, bare names, etc. — outside the supported form

        col = table.c[field]
        return col == value if op == "==" else col != value

    def evaluate(self, doc: dict, user: User, *, doctype_name: str = "") -> bool:
        """Python-level evaluation against a single already-fetched document.

        Fails CLOSED: an unevaluable expression (typo, unsupported syntax,
        field missing from *doc*, ...) denies rather than grants — the
        opposite default would turn a broken permission rule into an open
        one. Logged so a misconfigured rule is visible to admins.
        """
        try:
            from simpleeval import simple_eval

            names = {
                "user": user.email,
                "owner": doc.get("owner"),
                "doc": doc,
            }
            return bool(simple_eval(self.expr, names=names))
        except Exception:
            logger.warning(
                "permissions.match_eval_error", doctype=doctype_name, match=self.expr
            )
            return False
