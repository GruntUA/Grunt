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
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# What a permission row can grant, in the order Studio lists them.
#   select - a narrow read for Link-field pickers (name, title, search fields);
#            implied by ``read``.
#   export / import / print / share / report - separate from read/write: a role
#            may see a document without taking it out of the system.
ACTIONS: tuple[str, ...] = (
    "read",
    "select",
    "write",
    "create",
    "delete",
    "export",
    "import",
    "print",
    "share",
    "report",
)

# One boolean per action - the format before ``actions`` (migration 0021).
_OLD_FLAGS = ("read", "select", "write", "create", "delete", "report")

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


def has_old_permission_flags(definition: dict) -> bool:
    """Whether a stored DocType *definition* still has permission rows with the
    old flags - stored before migration 0021, which converts them."""
    return any(
        isinstance(row, dict) and any(flag in row for flag in _OLD_FLAGS)
        for key in ("permissions", "permissions_base")
        for row in definition.get(key) or []
    )


class DocPermission(BaseModel):
    """Pydantic model for a single permission row inside DocType metadata."""

    model_config = ConfigDict(extra="ignore")

    role: str
    # Granted actions, from ``ACTIONS``.
    actions: list[str] = []
    # Row-level filter - e.g. "owner == user", "team.lead == user"
    match: str | None = None
    # Fields hidden for this role (field names)
    hidden_fields: list[str] = []

    def grants(self, action: str) -> bool:
        """Whether this row grants *action* - ``read`` implies ``select``."""
        if action in self.actions:
            return True
        return action == "select" and "read" in self.actions

    @model_validator(mode="before")
    @classmethod
    def _no_old_flags(cls, data: Any) -> Any:
        # Ignored, an old flag would grant nothing without a word - refuse it.
        if isinstance(data, dict):
            old = [k for k in _OLD_FLAGS if k in data]
            if old:
                raise ValueError(
                    f"Permission row for {data.get('role')!r} uses old flags {old}: "
                    'list them as "actions": [...]'
                )
        return data

    @field_validator("actions")
    @classmethod
    def _known_actions(cls, value: list[str]) -> list[str]:
        # A misspelt action would deny silently - refuse it on save/load.
        unknown = [a for a in value if a not in ACTIONS]
        if unknown:
            raise ValueError(f"Unknown permission actions {unknown}: expected {list(ACTIONS)}")
        # One order everywhere: stored == JSON compares rows, not spellings.
        return [a for a in ACTIONS if a in value]

    @field_validator("match")
    @classmethod
    def _supported_match(cls, value: str | None) -> str | None:
        # A rule the predicate compiler can't translate would deny silently;
        # refuse it when the DocType is saved or loaded instead.
        return validate_match(value)
