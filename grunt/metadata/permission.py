"""DocType permission metadata model.

Lives in the metadata layer (no dependency on ``grunt.document.base``) so that
``grunt.metadata.doctype`` can reference it during bootstrap without importing a
Document controller - which would invert the metadata->document layering and
create an import cycle.

Permissions are stored inline on the owning DocType (``doctype.permissions``,
a list of these) and edited in the Studio DocType builder's "Дозволи" tab via
the ``DocPermission`` child schema. There is no standalone permission store.
"""

import re

from pydantic import BaseModel, ConfigDict, field_validator

# The ``match`` grammar: "<field> == <value>" / "<field> != <value>".
#   <field>  a document field, or "<link_field>.<target_field>" for a single
#            Link hop.
#   <value>  the bare word `user` (the current user's email) or a quoted literal.
# Compiled to a query predicate by ``grunt.permissions.match.PermissionMatch``.
MATCH_RE = re.compile(
    r"^(?P<field>[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)"
    r"\s*(?P<op>==|!=)\s*(?P<value>.+)$"
)


def is_literal(raw_value: str) -> bool:
    """A quoted string literal (``'x'`` / ``"x"``)."""
    return len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in "'\""


def validate_match(expr: str | None) -> str | None:
    """*expr* stripped (``None`` when empty), or ``ValueError`` when it is outside
    the grammar - a rule nobody can enforce must not be saved."""
    if expr is None or not expr.strip():
        return None
    expr = expr.strip()
    m = MATCH_RE.match(expr)
    if m is None or (
        m.group("value").strip() != "user" and not is_literal(m.group("value").strip())
    ):
        raise ValueError(
            f"Unsupported match {expr!r}: expected <field> == user, <field> != 'value' "
            "or <link_field>.<field> == user"
        )
    return expr


class DocPermission(BaseModel):
    """Pydantic model for a single permission row inside DocType metadata."""

    model_config = ConfigDict(extra="ignore")

    role: str
    read: bool = False
    # Narrow read for Link-field pickers: resolve/search name + title + search
    # fields only. Implied by ``read``. See ``PermissionAction``.
    select: bool = False
    write: bool = False
    create: bool = False
    delete: bool = False
    report: bool = False
    # Row-level filter - e.g. "owner == user", "team.lead == user"
    match: str | None = None
    # Fields hidden for this role (field names)
    hidden_fields: list[str] = []

    @field_validator("match")
    @classmethod
    def _supported_match(cls, value: str | None) -> str | None:
        # A rule the predicate compiler can't translate would deny silently;
        # refuse it when the DocType is saved or loaded instead.
        return validate_match(value)
