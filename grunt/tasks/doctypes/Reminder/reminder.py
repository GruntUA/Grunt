"""Reminder controller - a personal "remind me" about a document.

Delivery lives in :mod:`grunt.tasks.reminders` (every minute).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import grunt
from grunt import _
from grunt.document.base import Document
from grunt.permissions.guards import doc_guard

# A little slack for a picker that still shows the current minute.
_PAST_GRACE = timedelta(minutes=1)


def _aware(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class Reminder(Document):
    """DocType controller for Reminder."""

    async def validate(self) -> None:
        when = _aware(self.get("remind_at"))
        if when is None:
            grunt.throw(_("Choose when to remind"), "VALIDATION_ERROR")

        previous = None
        if self.id:
            previous = await grunt.db.get_value("Reminder", self.id, "remind_at")
        moved = previous is None or _aware(previous) != when
        if moved:
            if when < datetime.now(UTC) - _PAST_GRACE:
                grunt.throw(_("The reminder time is in the past"), "VALIDATION_ERROR")
            self.notified = False  # a new time means a new reminder

        ref_dt, ref_name = self.get("reference_doctype"), self.get("reference_name")
        if bool(ref_dt) != bool(ref_name):
            grunt.throw(_("Set both the document type and the document"), "VALIDATION_ERROR")
        if ref_dt and ref_name:
            await doc_guard(ref_dt, str(ref_name))  # only about what you can read
