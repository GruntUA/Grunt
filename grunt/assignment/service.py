"""Assignment Service — orchestration for automatic document assignment."""

from __future__ import annotations

import json
from typing import Any

import grunt
from grunt.log import log


class AssignmentService:
    """Оркестратор правил автоматичного призначення документів."""

    async def evaluate_and_assign(self, doctype: str, doc: dict[str, Any]) -> None:
        """Перевірити всі enabled правила для DocType та застосувати відповідні.

        Caller must already have an active grunt context — called synchronously
        from document lifecycle hooks (see hooks.py), which run inside the
        request's own write_guard-verified context.

        Args:
            doctype: Назва DocType документа (напр. "Invoice").
            doc: Дані документа {id, name, status, ...}.
        """
        try:
            rules = await self._get_enabled_rules(doctype)
            if not rules:
                return

            await self.apply_matching_rules(doctype, rules, doc)

        except Exception as exc:
            log.exception("assignment.evaluate_error", doctype=doctype, exc_info=exc)

    async def apply_matching_rules(
        self,
        doctype: str,
        rules: list[dict[str, Any]],
        doc: dict[str, Any],
    ) -> None:
        """Apply all matching assignment rules for a document."""
        from grunt.assignment.doctypes.AssignmentRule.assignment_rule import (
            AssignmentRule,
        )

        for rule_data in rules:
            rule = AssignmentRule("AssignmentRule", rule_data)
            if not rule.match(doc):
                continue
            await self.apply_rule(doctype, rule_data, doc)

    async def apply_rule(
        self,
        doctype: str,
        rule_data: dict[str, Any],
        doc: dict[str, Any],
    ) -> None:
        """Apply one assignment rule and persist ToDo/log entries."""
        assign_to_user = rule_data.get("assign_to_user")
        assign_to_role = rule_data.get("assign_to_role")
        rule_id = rule_data.get("name")

        if assign_to_user:
            await self._assign_to_user(doctype, doc, str(assign_to_user), rule_id)
            return

        if assign_to_role:
            await self._assign_to_role(doctype, doc, str(assign_to_role), rule_id)

    async def preview_rule(self, rule_id: str, test_doc: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a rule against a sample document and return preview details."""
        from grunt.assignment.doctypes.AssignmentRule.assignment_rule import (
            AssignmentRule,
        )
        from grunt.auth.doctypes.User.user import get_user_by_id

        rule = await grunt.get_doc(AssignmentRule, rule_id)

        matched = rule.match(test_doc)
        filters = rule.parsed_filters()

        will_assign_to: list[str] = []
        if matched:
            if rule.assign_to_user:
                will_assign_to.append(rule.assign_to_user)
            elif rule.assign_to_role:
                ur_rows = await grunt.get_list(
                    "UserRole",
                    filters={"role_name": rule.assign_to_role, "parent_doctype": "User"},
                    fields=["parent_name"],
                    limit=500,
                )
                for ur in ur_rows:
                    u = await get_user_by_id(ur["parent_name"])
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

    # ------------------------------------------------------------------
    # Приватні допоміжні методи оркестратора
    # ------------------------------------------------------------------

    async def _get_enabled_rules(self, doctype: str) -> list[dict]:
        """Завантажити всі enabled правила для DocType з БД."""
        from grunt.local import require_session

        try:
            async with grunt.context(require_session()):
                rows = await grunt.db.get_all(
                    "AssignmentRule",
                    filters={"doctype_target": doctype, "enabled": True},
                    fields=[
                        "name",
                        "doctype_target",
                        "filters",
                        "assign_to_role",
                        "assign_to_user",
                    ],
                    limit=100,
                )

            rules = []
            for row in rows:
                try:
                    filters = json.loads(row["filters"]) if row.get("filters") else {}
                except json.JSONDecodeError:
                    filters = {}

                rules.append(
                    {
                        "name": row["name"],
                        "doctype_target": row["doctype_target"],
                        "filters": filters,
                        "assign_to_role": row.get("assign_to_role"),
                        "assign_to_user": row.get("assign_to_user"),
                    }
                )

            return rules
        except Exception as exc:
            log.exception("assignment.load_rules_error", doctype=doctype, exc_info=exc)
            return []

    async def _assign_to_user(
        self,
        doctype: str,
        doc: dict[str, Any],
        user_email: str,
        rule_id: str | None,
    ) -> None:
        from grunt.assignment.doctypes.AssignmentLog.assignment_log import (
            AssignmentLog,
        )

        try:
            await self._create_todo(doctype, doc, user_email)
            await AssignmentLog.create(
                rule_id=rule_id,
                doctype_affected=doctype,
                document_id=doc.get("name") or "",
                assigned_to=user_email,
                assignment_method="user",
                status="Success",
            )
            log.info(
                "assignment.assigned_user", doctype=doctype, doc_id=doc.get("name"), user=user_email
            )
        except Exception as exc:
            log.exception(
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
        rule_id: str | None,
    ) -> None:
        from grunt.assignment.doctypes.AssignmentLog.assignment_log import (
            AssignmentLog,
        )
        from grunt.auth.doctypes.User.user import get_user_by_id
        from grunt.local import require_session

        try:
            async with grunt.system_context(require_session()):
                ur_rows = await grunt.db.get_all(
                    "UserRole",
                    filters={"role_name": role, "parent_doctype": "User"},
                    fields=["parent_name"],
                    limit=500,
                )

            user_ids = [r["parent_name"] for r in ur_rows]
            if not user_ids:
                log.info("assignment.no_users_in_role", doctype=doctype, role=role)
                return

            for user_id in user_ids:
                user = await get_user_by_id(user_id)
                if not user or not user.is_active:
                    continue

                await self._create_todo(doctype, doc, user.email)
                await AssignmentLog.create(
                    rule_id=rule_id,
                    doctype_affected=doctype,
                    document_id=doc.get("name") or "",
                    assigned_to=user.email,
                    assignment_method="role",
                    status="Success",
                )

            log.info(
                "assignment.assigned_role",
                doctype=doctype,
                doc_id=doc.get("name"),
                role=role,
                user_count=len(user_ids),
            )
        except Exception as exc:
            log.exception("assignment.assign_role_error", doctype=doctype, role=role, exc_info=exc)

    async def _create_todo(self, doctype: str, doc: dict[str, Any], owner_email: str) -> None:
        """Assign *doc* to *owner_email* via a ToDo row (idempotent per doc+user).

        Goes through ``new_doc`` — not ``bulk_insert`` — so the ``ToDo``
        ``after_insert`` hook fires and the assignee gets notified.
        """
        from grunt.local import require_session

        ref_id = doc.get("name") or doc.get("id")

        async with grunt.system_context(require_session()):
            already = await grunt.db.exists(
                "ToDo",
                {
                    "reference_doctype": doctype,
                    "reference_id": ref_id,
                    "assigned_to": owner_email,
                    "status": "Open",
                },
            )
            if already:
                return
            from grunt.tasks.doctypes.ToDo.to_do import auto_assign_note

            await grunt.new_doc(
                "ToDo",
                {
                    "description": auto_assign_note(doctype, ref_id),
                    "reference_doctype": doctype,
                    "reference_id": ref_id,
                    "assigned_to": owner_email,
                    "status": "Open",
                },
            )


assignment_service = AssignmentService()
