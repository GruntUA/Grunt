"""AssignmentRule DocType controller."""

import json
from typing import Any

from grunt.api.context import whitelist
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
lazy from grunt.auth.users import get_user_by_id
lazy from grunt.document.api import documents


class AssignmentRule(Document):
    """AssignmentRule DocType controller.

    Інкапсулює логіку перевірки фільтрів і застосування правила призначення.
    """

    # Lifecycle hooks

    async def validate(self) -> None:
        """Перевірити коректність JSON у полі filters."""
        if self.filters:
            try:
                json.loads(self.filters)
            except json.JSONDecodeError, TypeError:
                throw(
                    _("The “Filters (JSON)” field must contain valid JSON.")
                    + ' Example: {"status": "Draft"}',
                    title=_("Validation error"),
                )

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
        filters = self.parsed_filters()
        if not filters:
            return True

        for field, condition in filters.items():
            value = doc.get(field)

            if isinstance(condition, dict):
                for op, target in condition.items():
                    if (
                        op == ">"
                        and not (value and value > target)
                        or op == ">="
                        and not (value is not None and value >= target)
                        or op == "<"
                        and not (value and value < target)
                        or op == "<="
                        and not (value is not None and value <= target)
                        or op == "!="
                        and value == target
                        or op == "in"
                        and value not in target
                    ):
                        return False
            else:
                if value != condition:
                    return False

        return True

    async def preview(self, test_doc: dict[str, Any]) -> dict[str, Any]:
        """Evaluate the rule against a sample document: does it match, and whom it assigns."""
        matched = self.match(test_doc)
        filters = self.parsed_filters()

        will_assign_to: list[str] = []
        if matched:
            if self.assign_to_user:
                will_assign_to.append(self.assign_to_user)
            elif self.assign_to_role:
                ur_rows = await documents.get_list(
                    "UserRole",
                    filters={"role_name": self.assign_to_role, "parent_doctype": "User"},
                    fields=["parent_name"],
                    limit=500,
                )
                for ur in ur_rows:
                    u = await get_user_by_id(ur["parent_name"])
                    if u and u.is_active:
                        will_assign_to.append(u.email)

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
    """Test an assignment rule against a sample document."""
    try:
        rule = await documents.get_doc(AssignmentRule, rule_id)
        return await rule.preview(test_doc)
    except Exception as exc:
        throw(str(exc))
        raise RuntimeError(str(exc)) from exc
