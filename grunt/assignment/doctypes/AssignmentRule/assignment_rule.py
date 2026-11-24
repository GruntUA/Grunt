"""AssignmentRule DocType controller."""

import json
from typing import Any

from grunt.api.context import whitelist
from grunt.assignment.conditions import matches
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
lazy from grunt.assignment.service import assignment_service
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.permissions.rbac import permission_checker

_JSON_FIELDS = {
    "filters": "Filters (JSON)",
    "unassign_condition": "Unassign when (JSON)",
    "close_condition": "Close when (JSON)",
}


class AssignmentRule(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    enabled: bool | None = None  # Enabled
    doctype_target: str  # Target DocType
    priority: int | None = None  # Priority
    filters: str | None = None  # Filters (JSON)
    days: list[str] | None = None  # Days of the week
    unassign_condition: str | None = None  # Unassign when (JSON)
    close_condition: str | None = None  # Close when (JSON)
    rule: str | None = None  # Assign
    field: str | None = None  # User field
    assign_to_group: str | None = None  # Assign to group
    assign_to_role: str | None = None  # Assign to Role
    assign_to_user: str | None = None  # Assign to User
    due_date_field: str | None = None  # Due date from
    last_user: str | None = None  # Last assigned
    description: str | None = None  # Description
    users: list[dict] = []  # Table: AssignmentRuleUser

    # end: auto-generated types

    """AssignmentRule DocType controller.

    Інкапсулює логіку перевірки фільтрів і застосування правила призначення.
    """

    # Lifecycle hooks

    async def validate(self) -> None:
        """The JSON fields must hold valid JSON; Based on Field needs the field."""
        for fieldname, label in _JSON_FIELDS.items():
            raw = getattr(self, fieldname, None)
            if raw and not isinstance(raw, dict):
                try:
                    json.loads(raw)
                except json.JSONDecodeError, TypeError:
                    throw(
                        _("The “%(field)s” field must contain valid JSON.") % {"field": _(label)}
                        + ' Example: {"status": "Draft"}',
                        title=_("Validation error"),
                    )
        if getattr(self, "rule", None) == "Based on Field" and not getattr(self, "field", None):
            throw(_("Based on Field needs the user field"), title=_("Validation error"))

    # Публічний API правила

    def parsed_filters(self) -> dict:
        """Повернути розпарсені filters або порожній dict."""
        raw = getattr(self, "filters", None)
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError, TypeError:
            return {}

    def match(self, doc: dict[str, Any]) -> bool:
        """Перевірити, чи документ відповідає умовам правила.

        Підтримує:
            {"status": "Draft"}           -> doc["status"] == "Draft"
            {"total": {">": 1000}}        -> doc["total"] > 1000
            {"status": "Draft", "qty": 5} -> AND по всіх умовах
        """
        return matches(self.parsed_filters(), doc)

    async def preview(self, test_doc: dict[str, Any]) -> dict[str, Any]:
        """Evaluate the rule against a sample document: does it match, and whom it assigns."""
        matched = self.match(test_doc)
        filters = self.parsed_filters()

        will_assign_to: list[str] = []
        if matched:
            rule = {**self.data, "filters": filters}
            # Without moving a round robin's turn.
            will_assign_to = await assignment_service.pick(
                self.doctype_target or "", rule, test_doc, persist=False
            )

        matching_fields = [field for field in filters if field in test_doc]

        return {
            "rule_id": self.name,
            "doctype_target": self.doctype_target,
            "filters": filters,
            "matched": matched,
            "matching_fields": matching_fields,
            "will_assign_to": will_assign_to,
            "message": (
                f"Rule matches! Will assign to {len(will_assign_to)} user(s)"
                if matched
                else "Rule does not match"
            ),
        }


# Whitelisted API


@whitelist()
async def test_rule(rule_id: str, test_doc: dict[str, Any]) -> dict[str, Any]:
    """Test an assignment rule against a sample document - for who may edit the
    rule: the answer names the users it would assign."""
    rule = await AssignmentRule.get_doc(rule_id)
    meta = await doctype_registry.get_meta("AssignmentRule")
    if meta is not None:
        await permission_checker.require(meta, "write", rule.data)
    try:
        return await rule.preview(test_doc)
    except Exception as exc:
        throw(str(exc))
        raise RuntimeError(str(exc)) from exc
