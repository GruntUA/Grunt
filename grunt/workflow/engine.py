"""Workflow engine — state machine for DocType documents."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.User import User
    from grunt.metadata.doctype import DocType, WorkflowState, WorkflowTransition

logger = structlog.get_logger()


class WorkflowEngine:
    async def get_state(self, doctype: DocType, doc: dict) -> WorkflowState | None:
        if not doctype.workflow:
            return None
        state_value = doc.get(doctype.workflow.state_field)
        return next(
            (s for s in doctype.workflow.states if s.name == state_value),
            None,
        )

    async def get_available_transitions(
        self,
        doctype: DocType,
        doc: dict,
        user: User,
    ) -> list[WorkflowTransition]:
        if not doctype.workflow:
            return []
        current_state = await self.get_state(doctype, doc)
        current_state_name = current_state.name if current_state else None

        available: list[WorkflowTransition] = []
        for t in doctype.workflow.transitions:
            if t.from_state != current_state_name:
                continue
            # Check roles
            if t.allowed_roles:
                user_roles = set(getattr(user, "roles", []) or [])
                if not user_roles.intersection(set(t.allowed_roles)) and not getattr(
                    user, "is_superadmin", False
                ):
                    continue
            # Check condition
            if t.condition and not self._eval_condition(t.condition, doc, user.email):
                continue
            available.append(t)
        return available

    async def apply_transition(
        self,
        doctype: DocType,
        doc_id: str,
        action: str,
        user: User,
        session: AsyncSession,
        engine: AsyncEngine,
    ) -> dict:
        from grunt.app import grunt

        # Get document
        doc = await grunt.get_doc(doctype.name, doc_id)

        available = await self.get_available_transitions(doctype, doc, user)
        transition = next((t for t in available if t.action == action), None)

        if not transition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Перехід недоступний",
            )

        if not doctype.workflow:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Документ не має налаштованого Workflow",
            )

        # Apply
        state_field = doctype.workflow.state_field
        await grunt.db.set_value(doctype.name, doc_id, state_field, transition.to_state)

        # Re-read updated document (set_value already flushed)
        updated_doc = await grunt.get_doc(doctype.name, doc_id)

        # Run controller after_save (so apps can react to state changes)
        from grunt.document.registry import document_registry  # noqa: PLC0415

        try:
            controller_cls = document_registry.get(doctype.name)
            controller = controller_cls(doctype.name, updated_doc, user, session)
            await controller.after_save()
        except Exception:  # noqa: BLE001
            logger.exception("workflow.controller_after_save_error", doctype=doctype.name)

        # Fire on_transition hooks
        from grunt.hooks import fire as fire_hook  # noqa: PLC0415

        try:
            await fire_hook(
                "on_transition",
                doctype=doctype.name,
                doc=updated_doc,
                from_state=doc.get(state_field),
                to_state=transition.to_state,
                action=action,
                user=user,
                session=session,
            )
        except Exception:  # noqa: BLE001
            logger.exception("hook.on_transition_error")

        # Fire after_save / after_update hooks (so doc_events work for transitions too)
        try:
            await fire_hook(
                "after_save",
                doctype=doctype.name,
                doc=updated_doc,
                user=user,
                session=session,
            )
        except Exception:  # noqa: BLE001
            logger.exception("hook.after_save_on_transition_error")

        # Log activity
        with contextlib.suppress(Exception):
            await self._log_activity(
                doctype=doctype.name,
                doc_id=doc_id,
                action="workflow_transition",
                user=user.email,
                details={
                    "from": doc.get(state_field),
                    "to": transition.to_state,
                    "action": action,
                },
                session=session,
            )

        # Broadcast WS
        with contextlib.suppress(Exception):
            from grunt.api.v1.ws import manager  # noqa: PLC0415

            await manager.broadcast_doc(
                doctype.name,
                doc_id,
                "workflow_transition",
                {"action": action, "to_state": transition.to_state},
            )

        # Return updated doc (already read above)
        return updated_doc

    async def _log_activity(
        self,
        doctype: str,
        doc_id: str,
        action: str,
        user: str,
        details: dict,
        session: AsyncSession,
    ) -> None:
        from grunt.app import grunt

        await grunt.new_doc(
            "ActivityLog",
            {
                "doctype": doctype,
                "doc_id": doc_id,
                "action": action,
                "user": user,
                "details": details,
            },
        )

    def _eval_condition(self, condition: str, doc: dict, user: str) -> bool:
        try:
            from simpleeval import simple_eval

            result = simple_eval(
                condition, functions={"now": datetime.now}, names={"doc": doc, "user": user}
            )
            return bool(result)
        except Exception:  # noqa: BLE001
            return True  # Don't block on error


workflow_engine = WorkflowEngine()
