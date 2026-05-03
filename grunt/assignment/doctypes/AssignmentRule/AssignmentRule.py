"""AssignmentRule DocType controller."""

from __future__ import annotations

import json
from typing import Any

import grunt
from grunt.assignment import assignment_service
from grunt.document.base import Document


class AssignmentRule(Document):
    """AssignmentRule DocType controller.

    Інкапсулює логіку перевірки фільтрів і застосування правила призначення.
    """

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def validate(self) -> None:
        """Перевірити коректність JSON у полі filters."""
        if self.filters:
            try:
                json.loads(self.filters)
            except (json.JSONDecodeError, TypeError):
                grunt.throw(
                    "Поле 'Filters (JSON)' має містити валідний JSON. "
                    'Приклад: {"status": "Draft"}',
                    title="Помилка валідації",
                )

    # ------------------------------------------------------------------
    # Публічний API правила
    # ------------------------------------------------------------------

    def parsed_filters(self) -> dict:
        """Повернути розпарсені filters або порожній dict."""
        raw = getattr(self, "filters", None)
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def match(self, doc: dict[str, Any]) -> bool:
        """Перевірити, чи документ відповідає умовам правила.

        Підтримує:
            {"status": "Draft"}           → doc["status"] == "Draft"
            {"total": {">": 1000}}        → doc["total"] > 1000
            {"status": "Draft", "qty": 5} → AND по всіх умовах
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

# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------


@grunt.whitelist()
async def test_rule(rule_id: str, test_doc: dict[str, Any]) -> dict[str, Any]:
    """Test an assignment rule against a sample document."""
    try:
        return await assignment_service.preview_rule(rule_id, test_doc)
    except Exception as exc:
        grunt.throw(str(exc))
        raise RuntimeError(str(exc))
