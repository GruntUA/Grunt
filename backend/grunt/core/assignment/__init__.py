"""Assignment Service — оркестратор автоматичного призначення документів за правилами.

Бізнес-логіка (перевірка фільтрів, створення ToDo, логування) інкапсульована
в контролерах DocType:
  - AssignmentRule.match(doc)  → перевірка умов
  - AssignmentRule.apply(doc)  → створення ToDo
  - AssignmentLog.create(...)  → запис у журнал
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from grunt.app import grunt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class AssignmentService:
    """Оркестратор правил автоматичного призначення документів."""

    async def evaluate_and_assign(
        self, doctype: str, doc: dict[str, Any], session: AsyncSession
    ) -> None:
        """Перевірити всі enabled правила для DocType та застосувати відповідні.

        Args:
            doctype: Назва DocType документа (напр. "Invoice").
            doc: Дані документа {id, name, status, ...}.
            session: Async DB session.
        """
        try:
            rules = await self._get_enabled_rules(doctype, session)
            if not rules:
                return

            from grunt.core.doctypes.assignment_rule.assignment_rule import (  # noqa: PLC0415
                AssignmentRule,
            )

            for rule_data in rules:
                rule = AssignmentRule("AssignmentRule", rule_data)
                if rule.match(doc):
                    await rule.apply(doc, session)

        except Exception as exc:
            logger.exception("assignment.evaluate_error", doctype=doctype, exc_info=exc)

    # ------------------------------------------------------------------
    # Приватні допоміжні методи оркестратора
    # ------------------------------------------------------------------

    async def _get_enabled_rules(self, doctype: str, session: AsyncSession) -> list[dict]:
        """Завантажити всі enabled правила для DocType з БД."""
        try:
            _tokens = grunt.set_context(session, None, None)
            try:
                rows = await grunt.db.get_all(
                    "AssignmentRule",
                    filters={"doctype_target": doctype, "enabled": True},
                    fields=[
                        "id",
                        "doctype_target",
                        "filters",
                        "assign_to_role",
                        "assign_to_user",
                    ],
                    limit=100,
                )
            finally:
                grunt.reset_context(_tokens)

            rules = []
            for row in rows:
                try:
                    filters = json.loads(row["filters"]) if row.get("filters") else {}
                except json.JSONDecodeError:
                    filters = {}

                rules.append(
                    {
                        "id": row["id"],
                        "doctype_target": row["doctype_target"],
                        "filters": filters,
                        "assign_to_role": row.get("assign_to_role"),
                        "assign_to_user": row.get("assign_to_user"),
                    }
                )

            return rules
        except Exception as exc:
            logger.exception("assignment.load_rules_error", doctype=doctype, exc_info=exc)
            return []

    # ------------------------------------------------------------------
    # Зворотна сумісність: _match_filters залишається для існуючих тестів
    # ------------------------------------------------------------------

    def _match_filters(self, doc: dict[str, Any], filters: dict) -> bool:
        """[Deprecated] Використовуй AssignmentRule.match() замість цього.

        Залишено для зворотної сумісності з тестами.
        Делегує до AssignmentRule.match().
        """
        from grunt.core.doctypes.assignment_rule.assignment_rule import (  # noqa: PLC0415
            AssignmentRule,
        )

        rule = AssignmentRule("AssignmentRule", {"filters": filters})
        return rule.match(doc)


assignment_service = AssignmentService()
