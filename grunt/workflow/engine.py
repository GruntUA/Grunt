"""Workflow engine — state machine for DocType documents.

A transition is applied through the regular update pipeline (``grunt.save_doc``),
so the controller's ``validate``/``after_save`` and every hook run as for any
save; :func:`current_transition` tells them which transition is in progress.

While a DocType has an active workflow (see grunt/workflow/guard.py):

* its state field changes only through transitions (the internal system user —
  imports, fixtures, migrations — is exempt);
* a state's ``edit_roles`` limits who may edit/delete the document in it;
* an ``on_edit`` transition is applied automatically when a user allowed to
  take it edits the document in its ``from_state``.

After a transition: activity log entry, the comment (``require_comment``) on
the document, notifications (``notify``, grunt/workflow/notify.py), the
``on_transition`` hook and a websocket broadcast.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from grunt import _, log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType, WorkflowState, WorkflowTransition

# Values key carrying the dialog's comment for a `require_comment` transition.
COMMENT_KEY = "__comment"


@dataclass(frozen=True, slots=True)
class ActiveTransition:
    """The transition being applied — visible to controllers via :func:`current_transition`."""

    doctype: str
    doc_id: str
    from_state: str | None
    to_state: str
    action: str
    transition: WorkflowTransition
    comment: str | None = None


_active: ContextVar[ActiveTransition | None] = ContextVar("grunt_workflow_transition", default=None)


def current_transition() -> ActiveTransition | None:
    """The workflow transition being saved right now, if any.

    Set while the update pipeline runs for a transition (a button or an
    ``on_edit`` transition), so ``validate``/``after_save`` can react to it::

        if (t := current_transition()) and t.to_state == "Approved": ...
    """
    return _active.get()


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
        *,
        on_edit: bool = False,
    ) -> list[WorkflowTransition]:
        """Transitions *user* may apply now — buttons, or with ``on_edit`` the automatic ones."""
        from grunt.workflow.registry import get_active_workflow

        workflow = await get_active_workflow(doctype.name)
        if not workflow:
            return []
        current_state = await self.get_state(doctype, doc)
        current_state_name = current_state.state if current_state else None

        available: list[WorkflowTransition] = []
        for t in workflow.transitions:
            if t.from_state != current_state_name or t.on_edit != on_edit:
                continue
            if not user_may_take(t, user):
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
            # this way — an RPC caller can't sneak other fields in via `values`.
            for fieldname in transition.prompt_fields:
                if fieldname in values:
                    updates[fieldname] = values[fieldname]

            if transition.condition:
                merged_doc = {**doc, **updates}
                if not self._eval_condition(transition.condition, merged_doc, user.email):
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
        # The full update pipeline (validate, after_save, hooks, versions) —
        # `grunt.save_doc` also enforces the doctype's own write permission,
        # so a reader can't move a document through its workflow.
        token = _active.set(active)
        try:
            updated = await grunt.save_doc(doctype.name, doc_id, updates)
        finally:
            _active.reset(token)

        await self.finish_transition(active, updated, user, session)
        return updated

    async def finish_transition(
        self,
        active: ActiveTransition,
        doc: dict,
        user: User,
        session: AsyncSession,
    ) -> None:
        """After a transition is saved: log, comment, notify, hooks, broadcast."""
        from grunt.events import fire as fire_hook
        from grunt.workflow.notify import notify_transition, previous_actor

        # Who performed the previous action — read before this one is logged.
        previous = None
        if "previous" in active.transition.notify:
            with contextlib.suppress(Exception):
                previous = await previous_actor(active.doctype, active.doc_id)

        with contextlib.suppress(Exception):
            await self._log_activity(
                doctype=active.doctype,
                doc_id=active.doc_id,
                action="Workflow",
                user=user.email,
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

        try:
            await notify_transition(active, doc, user, previous=previous)
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

        with contextlib.suppress(Exception):
            from grunt.api.v1.ws import manager

            await manager.broadcast_doc(
                active.doctype,
                active.doc_id,
                "workflow_transition",
                {"action": active.action, "to_state": active.to_state},
            )

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

        async with grunt.system_context(session):
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


def user_may_take(transition: WorkflowTransition, user: User) -> bool:
    """Role check of a transition (System Manager may take any)."""
    if not transition.allowed_roles:
        return True
    roles = set(getattr(user, "roles", []) or [])
    return bool(roles.intersection(transition.allowed_roles)) or "System Manager" in roles


def state_updates(workflow: Any, to_state: str) -> dict[str, Any]:
    """Fields written on entering *to_state*: the state itself and its ``update_field``."""
    updates: dict[str, Any] = {workflow.state_field: to_state}
    state = next((s for s in workflow.states if s.state == to_state), None)
    if state and state.update_field:
        updates[state.update_field] = state.update_value
    return updates


async def _add_comment(active: ActiveTransition) -> None:
    """The transition's comment on the document's comment thread."""
    from html import escape

    import grunt

    text = escape(active.comment or "").replace("\n", "<br>")
    await grunt.new_doc(
        "Comment",
        {
            "reference_doctype": active.doctype,
            "reference_id": active.doc_id,
            "content": f"<p><strong>{escape(active.action)}</strong></p><p>{text}</p>",
            "comment_type": "Comment",
        },
    )


workflow_engine = WorkflowEngine()
