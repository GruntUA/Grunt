"""Workflow engine - state machine for DocType documents.

A transition is applied through the regular update pipeline (``grunt.save_doc``),
so the controller's ``validate``/``after_save`` and every hook run as for any
save; :func:`grunt.workflow.transition.current_transition` tells them which
transition is in progress.

While a DocType has an active workflow (see grunt/workflow/guard.py):

* its state field changes only through transitions (the internal system user -
  imports, fixtures, migrations - is exempt);
* a state's ``edit_roles`` limits who may edit/delete the document in it;
* an ``on_edit`` transition is applied automatically when a user allowed to
  take it edits the document in its ``from_state``.

After a transition: activity log entry, the comment (``require_comment``) on
the document, notifications (``notify``, grunt/workflow/notify.py), the
``on_transition`` hook and a websocket broadcast.
"""

import contextlib
from datetime import datetime
from html import escape
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.db.commit import on_commit
from grunt.document.api import documents
from grunt.events import fire as fire_hook
from grunt.i18n import _
from grunt.local import as_system
from grunt.log import log
from grunt.permissions.perms import ALL, user_perms
from grunt.permissions.roles import get_roles
from grunt.workflow.actors import previous_actor
from grunt.workflow.registry import get_active_workflow
from grunt.workflow.transition import ActiveTransition, _active, user_may_take
lazy from grunt.api.v1.ws import manager
lazy from grunt.metadata.doctype import DocType, WorkflowState, WorkflowTransition
lazy from grunt.notification.service import notification_service

# Values key carrying the dialog's comment for a `require_comment` transition.
COMMENT_KEY = "__comment"


class WorkflowEngine:
    async def get_state(self, doctype: DocType, doc: dict) -> WorkflowState | None:
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
        user: str,
        *,
        on_edit: bool = False,
    ) -> list[WorkflowTransition]:
        """Transitions *user* may apply now - buttons, or with ``on_edit`` the automatic ones."""
        workflow = await get_active_workflow(doctype.name)
        if not workflow:
            return []
        current_state = await self.get_state(doctype, doc)
        current_state_name = current_state.state if current_state else None

        available: list[WorkflowTransition] = []
        roles = await get_roles(user)
        unrestricted = ALL in await user_perms(user)
        for t in workflow.transitions:
            if t.from_state != current_state_name or t.on_edit != on_edit:
                continue
            if not user_may_take(t, roles, unrestricted=unrestricted):
                continue
            # Check condition - transitions with prompt_fields defer this check
            # to apply_transition(), once the dialog values are merged in, since
            # the condition often depends on a field the dialog itself fills in.
            if (
                t.condition
                and not t.prompt_fields
                and not self._eval_condition(t.condition, doc, user)
            ):
                continue
            available.append(t)
        return available

    async def apply_transition(
        self,
        doctype: DocType,
        doc_id: str,
        action: str,
        user: str,
        session: AsyncSession,
        engine: AsyncEngine,
        values: dict | None = None,
    ) -> dict:
        doc = await documents.get_doc(doctype.name, doc_id)

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

        values = dict(values or {})
        comment = str(values.pop(COMMENT_KEY, None) or "").strip() or None
        if transition.require_comment and not comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_("Add a comment"),
            )

        updates: dict = state_updates(workflow, transition.to_state)
        if transition.prompt_fields:
            # Only fields the transition explicitly asks for can be written
            # this way - an RPC caller can't sneak other fields in via `values`.
            for fieldname in transition.prompt_fields:
                if fieldname in values:
                    updates[fieldname] = values[fieldname]

            if transition.condition:
                merged_doc = {**doc, **updates}
                if not self._eval_condition(transition.condition, merged_doc, user):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=_("Fill in the required fields"),
                    )

        active = ActiveTransition(
            doctype=doctype.name,
            doc_id=doc["name"],
            from_state=doc.get(workflow.state_field),
            to_state=transition.to_state,
            action=action,
            transition=transition,
            comment=comment,
        )
        # The full update pipeline (validate, after_save, hooks, versions) -
        # `grunt.save_doc` also enforces the doctype's own write permission,
        # so a reader can't move a document through its workflow.
        token = _active.set(active)
        try:
            updated = await documents.save_doc(doctype.name, doc_id, updates)
        finally:
            _active.reset(token)

        await self.finish_transition(active, updated, user, session)
        return updated

    async def finish_transition(
        self,
        active: ActiveTransition,
        doc: dict,
        user: str,
        session: AsyncSession,
    ) -> None:
        """After a transition is saved: log, comment, notify, hooks, broadcast."""
        # Who performed the previous action - read before this one is logged
        # (a "Previous actor" recipient of the transition's notifications).
        previous = None
        with contextlib.suppress(Exception):
            previous = await previous_actor(active.doctype, active.doc_id)

        with contextlib.suppress(Exception):
            await self._log_activity(
                doctype=active.doctype,
                doc_id=active.doc_id,
                action="Workflow",
                user=user,
                details={
                    "from": active.from_state,
                    "to": active.to_state,
                    "action": active.action,
                    "comment": active.comment,
                },
                session=session,
            )

        if active.comment:
            try:
                await _add_comment(active)
            except Exception:
                log.exception("workflow.comment_error", doctype=active.doctype)

        # The transition's Notification rules (event on_transition) - here, in
        # the transaction, not in a worker: the previous actor is known now.
        try:
            await notification_service.evaluate_rules(
                session,
                "on_transition",
                active.doctype,
                doc,
                user,
                extra={
                    "action": active.action,
                    "from_state": active.from_state,
                    "to_state": active.to_state,
                    "comment": active.comment or "",
                    "previous": previous or "",
                },
            )
        except Exception:
            log.exception("workflow.notify_error", doctype=active.doctype)

        try:
            await fire_hook(
                "on_transition",
                doctype=active.doctype,
                doc=doc,
                from_state=active.from_state,
                to_state=active.to_state,
                action=active.action,
                comment=active.comment,
                user=user,
                session=session,
            )
        except Exception:
            log.exception("hook.on_transition_error")

        doctype, doc_id = active.doctype, active.doc_id
        data = {"action": active.action, "to_state": active.to_state}

        async def announce() -> None:
            with contextlib.suppress(Exception):
                await manager.broadcast_doc(doctype, doc_id, "workflow_transition", data)

        # After the commit - an open form reloads the document in its new state.
        on_commit(announce)

    async def _log_activity(
        self,
        doctype: str,
        doc_id: str,
        action: str,
        user: str,
        details: dict,
        session: AsyncSession,
    ) -> None:
        with as_system(session):
            await documents.new_doc(
                "ActivityLog",
                {
                    "ref_doctype": doctype,
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


def state_updates(workflow: Any, to_state: str) -> dict[str, Any]:
    """Fields written on entering *to_state*: the state itself and its ``update_field``."""
    updates: dict[str, Any] = {workflow.state_field: to_state}
    state = next((s for s in workflow.states if s.state == to_state), None)
    if state and state.update_field:
        updates[state.update_field] = state.update_value
    return updates


async def _add_comment(active: ActiveTransition) -> None:
    """The transition's comment on the document's comment thread."""
    text = escape(active.comment or "").replace("\n", "<br>")
    await documents.new_doc(
        "Comment",
        {
            "reference_doctype": active.doctype,
            "reference_id": active.doc_id,
            "content": f"<p><strong>{escape(active.action)}</strong></p><p>{text}</p>",
            "comment_type": "Comment",
        },
    )


workflow_engine = WorkflowEngine()
