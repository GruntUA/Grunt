"""A single parsed DocPermission.match expression.

``match`` (e.g. ``"owner == user"``, ``"team.lead == user"``) is translated to a
query predicate (``grunt.query.nodes``) and nothing else: lists filter by it in
SQL, a single document is decided by evaluating the *same* predicate against
its row (``grunt.permissions.query.row_allowed``). There used to be a second,
per-document evaluator (``simpleeval``) accepting a wider grammar - a rule could
open a document by its link yet keep it out of every list. One translation
makes that drift impossible.

Grammar: ``<field> (==|!=) (user|'literal')``, where ``<field>`` is a document
field or one Link hop ``<link_field>.<target_field>``. ``validate_match``
(``grunt.metadata.permission``) rejects anything else when the DocType is
saved or loaded.
"""

from collections.abc import Collection

from grunt.metadata.permission import MATCH_RE, is_literal
from grunt.metadata.registry import doctype_registry
from grunt.query.nodes import Cmp, Expr, Linked
lazy from grunt.document.meta import Meta
lazy from grunt.metadata.doctype import DocType


def _operand(raw_value: str, user: str | None) -> tuple[bool, str]:
    """Resolve the RHS of a match expression to a concrete string.

    ``(True, value)`` for the bare word ``user`` or a quoted literal;
    ``(False, "")`` for anything else (numbers, bare names) - which the caller
    must treat as "outside the supported grammar" and reject.
    """
    if raw_value == "user":
        # Nobody in context matches no one - never the rows with an empty owner.
        return (True, user) if user else (False, "")
    if is_literal(raw_value):
        return True, raw_value[1:-1]
    return False, ""


async def _resolve_link_target(
    doctype: DocType | Meta, link_fn: str
) -> tuple[str, Collection[str]] | None:
    """``(target_doctype_name, target_columns)`` for the Link field *link_fn* on
    *doctype*, or ``None`` when *link_fn* is not a Link (or its target DocType
    can't be loaded)."""
    field = next((f for f in doctype.fields if f.fieldname == link_fn), None)
    if field is None or not field.has_trait("link") or not field.options:
        return None

    target_dt = await doctype_registry.get_meta(field.options)
    if target_dt is None:
        return None
    return field.options, target_dt.columns


class PermissionMatch:
    """A parsed ``match`` expression, translated to a query predicate."""

    def __init__(self, expr: str) -> None:
        self.expr = expr.strip()
        self._parsed = self._parse()

    def _parse(self) -> tuple[str, str, str] | None:
        """Return ``(field, op, raw_value)`` for the narrow SQL-translatable
        form, or None when *expr* isn't in that form (arbitrary boolean
        logic, non-string/non-`user` literals, ...).
        """
        m = MATCH_RE.match(self.expr)
        if not m:
            return None
        return m.group("field"), m.group("op"), m.group("value").strip()

    async def to_expr(
        self, columns: Collection[str], user: str | None, doctype: DocType | Meta | None = None
    ) -> Expr | None:
        """The rule as a query predicate, for row-level list/count filtering.

        Returns None when this expression can't be translated - the caller
        must treat that as "can't enforce this rule" (deny/skip), never as
        "unrestricted", or an unparseable rule would silently expose every
        row instead of none.

        A ``link_field.target_field`` expression needs *doctype* (to resolve
        the Link's target) and becomes a ``Linked`` node: ``link_field`` among
        the target rows whose ``target_field`` is the value.
        """
        if self._parsed is None:
            return None
        field, op, raw_value = self._parsed
        ok, value = _operand(raw_value, user)
        if not ok:
            return None  # numbers, bare names, etc. - outside the supported form

        if "." not in field:
            if field not in columns:
                return None
            return Cmp(field, "eq" if op == "==" else "ne", value)

        link_fn, sub_fn = field.split(".", 1)
        if doctype is None or link_fn not in columns:
            return None
        resolved = await _resolve_link_target(doctype, link_fn)
        if resolved is None:
            return None
        target_name, target_columns = resolved
        if sub_fn not in target_columns:
            return None
        return Linked(link_fn, target_name, Cmp(sub_fn, "eq", value), negate=op != "==")
