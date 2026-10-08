"""AutoRepeat controller - validates the rule and keeps its schedule current.

The copying itself lives in :mod:`grunt.tasks.auto_repeat` (daily job).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import grunt
from grunt import _
from grunt.document.base import Document
from grunt.permissions.rbac import permission_checker
from grunt.tasks.auto_repeat import (
    FREQUENCIES,
    MONTHS_BY_FREQUENCY,
    anchor_day,
    as_date,
    first_date,
    status_for,
)

# Changing any of these re-plans the next run.
_SCHEDULE_FIELDS = (
    "reference_doctype",
    "reference_document",
    "frequency",
    "repeat_on_day",
    "repeat_on_last_day",
    "start_date",
    "end_date",
    "disabled",
)


class AutoRepeat(Document):
    """DocType controller for AutoRepeat."""

    reference_doctype: str
    reference_document: str
    frequency: str

    async def validate(self) -> None:
        await self._validate_reference()
        self._validate_schedule()

        prev: dict[str, Any] = {}
        if self.id:
            prev = (
                await grunt.db.get_value(
                    "AutoRepeat", self.id, list(_SCHEDULE_FIELDS), as_dict=True
                )
                or {}
            )
        replan = (
            not prev
            or not self.get("next_schedule_date")
            or any(prev.get(f) != self.get(f) for f in _SCHEDULE_FIELDS)
        )
        if replan and not self.get("disabled"):
            self.next_schedule_date = first_date(
                as_date(self.get("start_date")) or date.today(),
                self.frequency,
                anchor_day(self.data),
                bool(self.get("repeat_on_last_day")),
                not_before=date.today(),
            )
        self.status = status_for(self.data, as_date(self.get("next_schedule_date")))

    async def _validate_reference(self) -> None:
        meta = await grunt.get_meta(self.reference_doctype)
        if meta is None:
            grunt.throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.reference_doctype},
                "VALIDATION_ERROR",
            )
        dt = meta.doc
        if dt.is_child or dt.is_singleton or dt.is_virtual or dt.name == "AutoRepeat":
            grunt.throw(
                _("Documents of “%(doctype)s” cannot be repeated") % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )

        # The template must be readable and new documents creatable - by whoever
        # sets the rule up, since copies are later made as the rule's owner.
        await grunt.get_doc(self.reference_doctype, self.reference_document)
        user = grunt.get_user()
        if not await permission_checker.check(user, meta, "create"):
            grunt.throw(
                _("You are not allowed to create “%(doctype)s” documents") % {"doctype": dt.name},
                "PERMISSION_DENIED",
            )

        date_field = (self.get("date_field") or "").strip()
        self.date_field = date_field or None
        if date_field:
            field = meta.get_field(date_field)
            if field is None or field.fieldtype not in ("Date", "Datetime"):
                grunt.throw(
                    _("“%(field)s” is not a date field of %(doctype)s")
                    % {"field": date_field, "doctype": dt.name},
                    "VALIDATION_ERROR",
                )

    def _validate_schedule(self) -> None:
        if self.frequency not in FREQUENCIES:
            grunt.throw(_("Unknown frequency: %(f)s") % {"f": self.frequency}, "VALIDATION_ERROR")
        day = self.get("repeat_on_day")
        if day and not 1 <= int(day) <= 31:
            grunt.throw(_("Day of month must be between 1 and 31"), "VALIDATION_ERROR")
        if self.frequency not in MONTHS_BY_FREQUENCY:
            self.repeat_on_day = None
            self.repeat_on_last_day = False
        start, end = as_date(self.get("start_date")), as_date(self.get("end_date"))
        if start and end and end < start:
            grunt.throw(_("End date cannot be before the start date"), "VALIDATION_ERROR")
