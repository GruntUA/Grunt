"""AssignmentRule DocType controller."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

import grunt
from grunt.app import grunt as grunt_app
from grunt.core.document.base import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


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

    async def apply(self, doc: dict[str, Any], session: AsyncSession) -> None:
        """Застосувати правило: створити ToDo(и) для відповідних користувачів.

        Викликати лише якщо match(doc) повернув True.
        """
        assign_to_user = getattr(self, "assign_to_user", None)
        assign_to_role = getattr(self, "assign_to_role", None)
        rule_id = getattr(self, "id", None)
        doctype = getattr(self, "doctype_target", "")

        if assign_to_user:
            await self._assign_to_user(doctype, doc, assign_to_user, session, rule_id)
        elif assign_to_role:
            await self._assign_to_role(doctype, doc, assign_to_role, session, rule_id)

    # ------------------------------------------------------------------
    # Приватні методи
    # ------------------------------------------------------------------

    async def _assign_to_user(
        self,
        doctype: str,
        doc: dict[str, Any],
        user_email: str,
        session: AsyncSession,
        rule_id: str | None = None,
    ) -> None:
        """Призначити документ конкретному користувачеві (create ToDo)."""
        from grunt.core.doctypes.user.user import SYSTEM_USER  # noqa: PLC0415
        from grunt.core.doctypes.assignment_log.assignment_log import (  # noqa: PLC0415
            AssignmentLog,
        )

        try:
            todo_doc = {
                "title": f"{doctype}: {doc.get('name', doc.get('id', 'Document'))}",
                "reference_type": doctype,
                "reference_name": doc.get("id") or doc.get("name"),
                "assigned_by": "system",
                "owner": user_email,
                "status": "Open",
            }

            _tokens = grunt_app.set_context(session, None, SYSTEM_USER)
            try:
                await grunt_app.bulk_insert("ToDo", [todo_doc])
            finally:
                grunt_app.reset_context(_tokens)

            await AssignmentLog.create(
                rule_id=rule_id,
                doctype_affected=doctype,
                document_id=doc.get("id") or doc.get("name") or "",
                assigned_to=user_email,
                assignment_method="user",
                status="Success",
                session=session,
            )

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
        self,
        doctype: str,
        doc: dict[str, Any],
        role: str,
        session: AsyncSession,
        rule_id: str | None = None,
    ) -> None:
        """Призначити документ всім активним користувачам ролі."""
        from grunt.core.doctypes.user.user import SYSTEM_USER  # noqa: PLC0415
        from grunt.core.doctypes.assignment_log.assignment_log import (  # noqa: PLC0415
            AssignmentLog,
        )
        from grunt.core.doctypes.user.user import get_user_by_id  # noqa: PLC0415

        try:
            _tokens = grunt_app.set_context(session, None, SYSTEM_USER)
            try:
                ur_rows = await grunt_app.db.get_all(
                    "UserRole",
                    filters={"role_name": role},
                    fields=["user_id"],
                    limit=500,
                )
            finally:
                grunt_app.reset_context(_tokens)

            user_ids = [r["user_id"] for r in ur_rows]

            if not user_ids:
                logger.info(
                    "assignment.no_users_in_role",
                    doctype=doctype,
                    role=role,
                )
                return

            for user_id in user_ids:
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

                _tokens2 = grunt_app.set_context(session, None, SYSTEM_USER)
                try:
                    await grunt_app.bulk_insert("ToDo", [todo_doc])
                finally:
                    grunt_app.reset_context(_tokens2)

                await AssignmentLog.create(
                    rule_id=rule_id,
                    doctype_affected=doctype,
                    document_id=doc.get("id") or doc.get("name") or "",
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


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------


@grunt.whitelist()
async def test_rule(rule_id: str, test_doc: dict[str, Any]) -> dict[str, Any]:
    """Test an assignment rule against a sample document."""
    from grunt.core.doctypes.user.user import get_user_by_id  # noqa: PLC0415

    try:
        raw = await grunt_app.get_doc("AssignmentRule", rule_id)
        rule = AssignmentRule("AssignmentRule", raw)

        matched = rule.match(test_doc)
        filters = rule.parsed_filters()

        will_assign_to: list[str] = []
        if matched:
            if rule.assign_to_user:
                will_assign_to.append(rule.assign_to_user)
            elif rule.assign_to_role:
                ur_rows = await grunt_app.get_list(
                    "UserRole",
                    filters={"role_name": rule.assign_to_role},
                    fields=["user_id"],
                    limit=500,
                )
                session = grunt_app._require_session()
                for ur in ur_rows:
                    u = await get_user_by_id(ur["user_id"], session)
                    if u and u.is_active:
                        will_assign_to.append(u.email)

        matching_fields = [field for field in filters if field in test_doc]

        return {
            "rule_id": rule_id,
            "doctype_target": rule.doctype_target,
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
    except Exception as exc:
        grunt_app.throw(str(exc))
