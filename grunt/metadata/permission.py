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


# Exactly one quoted token - ``'Open' and owner == 'x'`` starts and ends with a
# quote too, but is not a literal.
_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def is_literal(raw_value: str) -> bool:
    """A single quoted string literal (``'x'`` / ``"x"``)."""
    return _LITERAL_RE.fullmatch(raw_value) is not None


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

    def grants(self, action: str) -> bool:
        """Whether this row grants *action* - ``read`` implies ``select``."""
        if getattr(self, action, False) is True:
            return True
        return action == "select" and self.read

    @field_validator("match")
    @classmethod
    def _supported_match(cls, value: str | None) -> str | None:
        # A rule the predicate compiler can't translate would deny silently;
        # refuse it when the DocType is saved or loaded instead.
        return validate_match(value)
