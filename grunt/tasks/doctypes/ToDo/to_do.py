"""ToDo controller.

A ToDo row *is* an assignment: someone (``assigned_to``) is put on the hook for
a document (``reference_doctype`` / ``reference_id``), optionally with a task
note in ``description``.

- on create        → ping the assignee
- on reassignment  → ping the new assignee
- on completion    → stamp ``completed_on`` / ``completed_by`` and tell whoever
                     created the assignment (``assigned_by``, falling back to
                     ``owner``); reopening clears the stamp
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from grunt.document.base import Document
from grunt.i18n import _, language_of, use_language
from grunt.log import log

_DONE_STATES = ("Closed", "Cancelled")

# A ToDo created without a real task note carries a boilerplate description:
# the frontend ``docsApi.assign`` writes ``"Assigned to <email>"``; the
# auto-assignment rules (see ``grunt.assignment.service``) write
# ``"Auto-assigned: <doctype> <id>"`` (``"Призначено:"`` in rows written before
# the English source). Any of them means "no note".
_PLACEHOLDER_PREFIXES = ("Assigned to ", "Auto-assigned:", "Призначено:")


def is_placeholder_note(note: str | None) -> bool:
    """True when *note* is auto-generated assignment boilerplate, not a real task."""
    return (note or "").strip().startswith(_PLACEHOLDER_PREFIXES)


def auto_assign_note(doctype: str, ref_id: str | None) -> str:
    """The boilerplate description an automatic assignment gets."""
    return f"Auto-assigned: {doctype} {ref_id or ''}".strip()


class ToDo(Document):
    """DocType controller for ToDo (assignment)."""

    description: str
    reference_doctype: str | None
    reference_id: str | None
    assigned_to: str | None
    assigned_by: str | None
    status: str

    _inserting: bool = False
    _prev: dict[str, Any] | None = None

    # ── lifecycle ────────────────────────────────────────────────────────

    async def before_insert(self) -> None:
        self._inserting = True
        if not self.get("assigned_by"):
            self.assigned_by = self._actor_email() or None
        if not self.get("assigned_on"):
            self.assigned_on = datetime.now(UTC)

    async def before_save(self) -> None:
        if self._inserting:
            return
        if self._prev is None:
            self._prev = (
                await self.grunt.db.get_value(
                    "ToDo", self.id, ["status", "assigned_to"], as_dict=True
                )
                or {}
            )

        was_done = self._prev.get("status") in _DONE_STATES
        is_done = self.status in _DONE_STATES
        if is_done and not was_done:
            if not self.get("completed_on"):
                self.completed_on = datetime.now(UTC)
            if not self.get("completed_by"):
                self.completed_by = self._actor_email() or None
        elif was_done and not is_done:
            # reopened — drop the stale completion stamp
            self.completed_on = None
            self.completed_by = None

    async def after_insert(self) -> None:
        await self._notify_assignee((self.assigned_to or "").strip())

    async def after_save(self) -> None:
        if self._inserting or self._prev is None:
            return
        prev = self._prev

        new_assignee = (self.assigned_to or "").strip()
        if new_assignee and new_assignee != (prev.get("assigned_to") or "").strip():
            await self._notify_assignee(new_assignee)

        if self.status == "Closed" and prev.get("status") != "Closed":
            await self._notify_completion()

    # ── helpers ─────────────────────────────────────────────────────────

    def _actor_email(self) -> str:
        return getattr(getattr(self, "user", None), "email", "") or ""

    def _target(self) -> str:
        ref_dt = (self.get("reference_doctype") or "").strip()
        ref_id = str(self.get("reference_id") or "").strip()
        return f"{ref_dt} {ref_id}".strip() or _("document")

    def _task_note(self) -> str:
        note = (self.get("description") or "").strip()
        return "" if is_placeholder_note(note) else note

    async def _deliver(self, user: str, subject: str, message: str) -> None:
        ref_dt = (self.get("reference_doctype") or "").strip()
        ref_id = str(self.get("reference_id") or "").strip()
        from grunt.notification.service import notification_service

        await notification_service.notify(
            self.session,
            user=user,
            doctype=ref_dt or "ToDo",
            doc_id=ref_id or (self.id or ""),
            subject=subject,
            message=message,
            email=True,
        )

    async def _notify_assignee(self, assignee: str) -> None:
        """Tell *assignee* they have a new assignment (skips self-assignment)."""
        if not assignee or assignee == self._actor_email():
            return
        note = self._task_note()
        try:
            # Stored text: compose it in the recipient's language.
            with use_language(await language_of(assignee)):
                target = self._target()
                subject = _("Assigned to you: %(target)s") % {"target": target}
                message = note or _("You have been assigned to %(target)s.") % {"target": target}
            await self._deliver(assignee, subject, message)
        except Exception:
            log.exception("todo.notify_assignee_failed", assignee=assignee)

    async def _notify_completion(self) -> None:
        """Tell whoever created the assignment that it is done."""
        recipient = (self.get("assigned_by") or self.get("owner") or "").strip()
        actor = self._actor_email()
        if not recipient or recipient == actor:
            return
        try:
            with use_language(await language_of(recipient)):
                target = self._target()
                subject = _("Task completed: %(target)s") % {"target": target}
                message = _("%(actor)s marked the task as done: %(task)s") % {
                    "actor": actor or _("The assignee"),
                    "task": self._task_note() or target,
                }
            await self._deliver(recipient, subject, message)
        except Exception:
            log.exception("todo.notify_completion_failed", recipient=recipient)
