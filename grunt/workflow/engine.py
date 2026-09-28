"""Workflow engine — state machine for DocType documents."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from grunt.i18n import _
from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType, WorkflowState, WorkflowTransition


class WorkflowEngine:
    async def get_state(self, doctype: DocType, doc: dict) -> WorkflowState | None:
        from grunt.workflow.registry import get_active_workflow

        workflow = await get_active_workflow(doctype.name)
        if not workflow:
            return None
        state_value = doc.get(workflow.state_field)
        return next(
            (s for s in workflow.states if s.state == state_value),
            None,
        )

    async def get_available_transitions(
        self,
        doctype: DocType,
        doc: dict,
        user: User,
    ) -> list[WorkflowTransition]:
        from grunt.workflow.registry import get_active_workflow

        workflow = await get_active_workflow(doctype.name)
        if not workflow:
            return []
        current_state = await self.get_state(doctype, doc)
        current_state_name = current_state.state if current_state else None

        available: list[WorkflowTransition] = []
        for t in workflow.transitions:
            if t.from_state != current_state_name:
                continue
            # Check roles
            if t.allowed_roles:
                user_roles = set(getattr(user, "roles", []) or [])
                allowed = user_roles.intersection(t.allowed_roles) or "System Manager" in user_roles
                if not allowed:
                    continue
            # Check condition — transitions with prompt_fields defer this check
            # to apply_transition(), once the dialog values are merged in, since
            # the condition often depends on a field the dialog itself fills in.
            if (
                t.condition
                and not t.prompt_fields
                and not self._eval_condition(t.condition, doc, user.email)
            ):
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
        values: dict | None = None,
    ) -> dict:
        import grunt
        from grunt.workflow.registry import get_active_workflow

        # Get document
        doc = await grunt.get_doc(doctype.name, doc_id)

        available = await self.get_available_transitions(doctype, doc, user)
        transition = next((t for t in available if t.action == action), None)

        if not transition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("The transition is unavailable"),
            )

        workflow = await get_active_workflow(doctype.name)
        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("The document has no Workflow configured"),
            )

        state_field = workflow.state_field
        updates: dict = {state_field: transition.to_state}
        if transition.prompt_fields:
            # Only fields the transition explicitly asks for can be written
            # this way — an RPC caller can't sneak other fields in via `values`.
            for fieldname in transition.prompt_fields:
                if values and fieldname in values:
                    updates[fieldname] = values[fieldname]

            if transition.condition:
                merged_doc = {**doc, **updates}
                if not self._eval_condition(transition.condition, merged_doc, user.email):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=_("Fill in the required fields"),
                    )

        # Apply — guarded `grunt.set_value` (not `grunt.db.set_value`), so this
        # still enforces the doctype's own write permission even when the
        # transition itself declares no `allowed_roles` (a reader with no
        # write access must not be able to move the document through its
        # workflow just because they can read it).
        await grunt.set_value(doctype.name, doc_id, updates)

        # Re-read updated document (set_value already flushed) as a bound controller
        # so apps can react to state changes via after_save() — .as_dict() below
        # reuses this same fetch for the hooks/return value, no second DB round-trip.
        controller = await grunt.get_doc_instance(doctype.name, doc_id)
        updated_doc = controller.as_dict()
        try:
            await controller.after_save()
        except Exception:
            log.exception("workflow.controller_after_save_error", doctype=doctype.name)

        # Fire on_transition hooks
        from grunt.events import fire as fire_hook

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
        except Exception:
            log.exception("hook.on_transition_error")

        # Fire after_save / after_update hooks (so doc_events work for transitions too)
        try:
            await fire_hook(
                "after_save",
                doctype=doctype.name,
                doc=updated_doc,
                user=user,
                session=session,
            )
        except Exception:
            log.exception("hook.after_save_on_transition_error")

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
            from grunt.api.v1.ws import manager

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
        import grunt

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
        except Exception:
            log.warning("workflow.condition_eval_failed", condition=condition, user=user)
            return True  # Don't block on error


workflow_engine = WorkflowEngine()
