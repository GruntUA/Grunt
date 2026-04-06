"""Assignment Service — автоматичне призначення документів за правилами."""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry
from grunt.app import grunt

logger = structlog.get_logger()


class AssignmentService:
    """Управління правилами автоматичного призначення документів."""

    async def evaluate_and_assign(
        self, doctype: str, doc: dict[str, Any], session: AsyncSession
    ) -> None:
        """Перевірити всі правила для DocType та призначити якщо відповідає умові.

        Args:
            doctype: Назва DocType документа
            doc: Дані документа {id, title, status, ...}
            session: Async DB session
        """
        try:
            # Завантажити правила з БД
            rules = await self._get_enabled_rules(doctype, session)
            if not rules:
                return

            # Для кожного правила перевірити filters
            for rule in rules:
                filters = rule.get("filters", {})
                assign_to_role = rule.get("assign_to_role")
                assign_to_user = rule.get("assign_to_user")
                rule_id = rule.get("id")

                # Пройти умови
                if self._match_filters(doc, filters):
                    # Визначити кого призначити
                    if assign_to_user:
                        # Конкретний користувач — пріоритет
                        await self._assign_to_user(doctype, doc, assign_to_user, session, rule_id)
                    elif assign_to_role:
                        # Всим користувачам ролі
                        await self._assign_to_role(doctype, doc, assign_to_role, session, rule_id)

        except Exception as exc:
            logger.exception("assignment.evaluate_error", doctype=doctype, exc_info=exc)

    async def _get_enabled_rules(self, doctype: str, session: AsyncSession) -> list[dict]:
        """Завантажити всі enabled правила для DocType."""
        try:
            _tokens = grunt.set_context(session, None, None)
            try:
                rows = await grunt.db.get_all(
                    "AssignmentRule",
                    filters={"doctype_target": doctype, "enabled": True},
                    fields=["id", "doctype_target", "filters", "assign_to_role", "assign_to_user"],
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

    def _match_filters(self, doc: dict[str, Any], filters: dict) -> bool:
        """Перевірити чи документ відповідає умовам фільтра.

        Підтримує:
            {"status": "Draft"}           → doc["status"] == "Draft"
            {"total": {">": 1000}}        → doc["total"] > 1000
            {"status": "Draft", "qty": 5} → обидва мають збігатися (AND)
        """
        if not filters:
            return True

        for field, condition in filters.items():
            value = doc.get(field)

            if isinstance(condition, dict):
                # Оператори: {">": 100}, {">=": 50}, {"<": 10}, {"<=": 20}, {"!=": "Draft"}
                for op, target in condition.items():
                    if op == ">" and not (value and value > target):
                        return False
                    elif op == ">=" and not (value is not None and value >= target):
                        return False
                    elif op == "<" and not (value and value < target):
                        return False
                    elif op == "<=" and not (value is not None and value <= target):
                        return False
                    elif op == "!=" and value == target:
                        return False
                    elif op == "in" and value not in target:
                        return False
            else:
                # Простий збіг: {"status": "Draft"}
                if value != condition:
                    return False

        return True

    async def _assign_to_user(
        self, doctype: str, doc: dict[str, Any], user_email: str, session: AsyncSession, rule_id: str | None = None
    ) -> None:
        """Призначити документ конкретному користувачеві (create ToDo)."""
        try:
            # Log assignment
            await self._log_assignment(
                rule_id=rule_id,
                doctype_affected=doctype,
                document_id=doc.get("id") or doc.get("name"),
                assigned_to=user_email,
                assignment_method="user",
                status="Success",
                session=session,
            )

            from grunt.app import grunt  # noqa: PLC0415
            from grunt.core.auth.models import SYSTEM_USER  # noqa: PLC0415

            todo_doc = {
                "title": f"{doctype}: {doc.get('name', doc.get('id', 'Document'))}",
                "reference_type": doctype,
                "reference_name": doc.get("id") or doc.get("name"),
                "assigned_by": "system",
                "owner": user_email,
                "status": "Open",
            }

            _tokens = grunt.set_context(session, None, SYSTEM_USER)
            try:
                await grunt.bulk_insert("ToDo", [todo_doc])
            finally:
                grunt.reset_context(_tokens)

            logger.info(
                "assignment.assigned_user",
                doctype=doctype,
                doc_id=doc.get("id"),
                user=user_email,
            )
        except Exception as exc:
            logger.exception(
                "assignment.assign_user_error",
                doctype=doctype,
                user=user_email,
                exc_info=exc,
            )

    async def _assign_to_role(
        self, doctype: str, doc: dict[str, Any], role: str, session: AsyncSession, rule_id: str | None = None
    ) -> None:
        """Призначити документ всім користувачам ролі."""
        try:
            from grunt.app import grunt  # noqa: PLC0415
            from grunt.core.auth.models import SYSTEM_USER  # noqa: PLC0415
            from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

            # Завантажити всіх користувачів з цієї ролі
            _tokens = grunt.set_context(session, None, SYSTEM_USER)
            try:
                ur_rows = await grunt.db.get_all(
                    "UserRole", filters={"role_name": role}, fields=["user_id"], limit=500
                )
            finally:
                grunt.reset_context(_tokens)
            user_ids = [r["user_id"] for r in ur_rows]

            if not user_ids:
                logger.info(
                    "assignment.no_users_in_role",
                    doctype=doctype,
                    role=role,
                )
                return

            for user_id in user_ids:
                # Завантажити email користувача
                from grunt.core.doctypes.User.User import get_user_by_id  # noqa: PLC0415

                user = await get_user_by_id(user_id, session)
                if not user or not user.is_active:
                    continue

                todo_doc = {
                    "title": f"{doctype}: {doc.get('name', doc.get('id', 'Document'))}",
                    "reference_type": doctype,
                    "reference_name": doc.get("id") or doc.get("name"),
                    "assigned_by": "system",
                    "owner": user.email,
                    "status": "Open",
                }

                _tokens2 = grunt.set_context(session, None, SYSTEM_USER)
                try:
                    await grunt.bulk_insert("ToDo", [todo_doc])
                finally:
                    grunt.reset_context(_tokens2)

                # Log each assignment
                await self._log_assignment(
                    rule_id=rule_id,
                    doctype_affected=doctype,
                    document_id=doc.get("id") or doc.get("name"),
                    assigned_to=user.email,
                    assignment_method="role",
                    status="Success",
                    session=session,
                )

            logger.info(
                "assignment.assigned_role",
                doctype=doctype,
                doc_id=doc.get("id"),
                role=role,
                user_count=len(user_ids),
            )
        except Exception as exc:
            logger.exception(
                "assignment.assign_role_error",
                doctype=doctype,
                role=role,
                exc_info=exc,
            )

    async def _log_assignment(
        self,
        rule_id: str | None,
        doctype_affected: str,
        document_id: str,
        assigned_to: str,
        assignment_method: str,
        status: str,
        error_message: str | None = None,
        filters_matched: bool = True,
        session: AsyncSession | None = None,
    ) -> None:
        """Log assignment to AssignmentLog DocType."""
        if not session:
            return

        try:
            from grunt.app import grunt  # noqa: PLC0415
            from grunt.core.auth.models import SYSTEM_USER  # noqa: PLC0415

            log_doc = {
                "rule_id": rule_id,
                "doctype_affected": doctype_affected,
                "document_id": document_id,
                "assigned_to": assigned_to,
                "assignment_method": assignment_method,
                "status": status,
                "error_message": error_message,
                "filters_matched": filters_matched,
            }

            _tokens = grunt.set_context(session, None, SYSTEM_USER)
            try:
                await grunt.bulk_insert("AssignmentLog", [log_doc])
            finally:
                grunt.reset_context(_tokens)
        except Exception as exc:
            logger.exception("assignment.log_error", exc_info=exc)


assignment_service = AssignmentService()
