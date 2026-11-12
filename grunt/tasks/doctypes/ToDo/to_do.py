"""ToDo controller.

A ToDo row *is* an assignment: someone (``assigned_to``) is put on the hook for
a document (``reference_doctype`` / ``reference_id``), optionally with a task
note in ``description``.

- on create        -> ping the assignee
- on reassignment  -> ping the new assignee
- on completion    -> stamp ``completed_on`` / ``completed_by`` and tell whoever
                     created the assignment (``assigned_by``, falling back to
                     ``owner``); reopening clears the stamp
"""

from datetime import UTC, datetime
from typing import Any

from grunt.document.base import Document
from grunt.i18n import _
from grunt.notification.events import trigger

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

    # lifecycle

    async def before_insert(self) -> None:
        self._inserting = True
        if not self.get("assigned_by"):
            self.assigned_by = self._actor_email() or None
        if not self.get("assigned_on"):
            self.assigned_on = datetime.now(UTC)

    async def before_save(self) -> None:
        if self._inserting or not self.id:
            return
        if self._prev is None:
            self._prev = (
                await self.grunt.db.get_value(
                    "ToDo", self.id, ["status", "assigned_to"], as_dict=True
                )
                or {}
            )

        was_done = (self._prev or {}).get("status") in _DONE_STATES
        is_done = self.status in _DONE_STATES
        if is_done and not was_done:
            if not self.get("completed_on"):
                self.completed_on = datetime.now(UTC)
            if not self.get("completed_by"):
                self.completed_by = self._actor_email() or None
        elif was_done and not is_done:
            # reopened - drop the stale completion stamp
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

    # helpers

    def _actor_email(self) -> str:
        return self.user or ""

    def _target(self) -> str:
        ref_dt = (self.get("reference_doctype") or "").strip()
        ref_id = str(self.get("reference_id") or "").strip()
        return f"{ref_dt} {ref_id}".strip() or _("document")

    def _task_note(self) -> str:
        note = (self.get("description") or "").strip()
        return "" if is_placeholder_note(note) else note

    async def _trigger(self, key: str, recipient: str, **extra: Any) -> None:
        """Code event *key* (its standard ``Notification`` says what and how)."""
        ref_dt = (self.get("reference_doctype") or "").strip()
        ref_id = str(self.get("reference_id") or "").strip()
        await trigger(
            key,
            doc={**self.data, "name": self.id},
            doctype="ToDo",
            link=(ref_dt, ref_id) if ref_dt and ref_id else None,
            recipients=[recipient],
            actor=self._actor_email(),
            # Callables run in each recipient's language.
            extra={"target": self._target, **extra},
            session=self.session,
        )

    async def _notify_assignee(self, assignee: str) -> None:
        """Tell *assignee* they have a new assignment (skips self-assignment)."""
        if not assignee or assignee == self._actor_email():
            return
        await self._trigger("grunt.todo.assigned", assignee, note=self._task_note())

    async def _notify_completion(self) -> None:
        """Tell whoever created the assignment that it is done."""
        recipient = (self.get("assigned_by") or self.get("owner") or "").strip()
        if not recipient or recipient == self._actor_email():
            return
        await self._trigger(
            "grunt.todo.completed", recipient, task=lambda: self._task_note() or self._target()
        )
