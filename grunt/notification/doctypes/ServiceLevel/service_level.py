"""ServiceLevel controller - validates an SLA policy against its DocType.

The tracking itself lives in :mod:`grunt.notification.sla`.
"""

from __future__ import annotations

import grunt
from grunt import _
from grunt.document.base import Document

_DATE_TYPES = ("Date", "Datetime")
_SYSTEM_DATES = ("created_at", "modified_at")


class ServiceLevel(Document):
    """DocType controller for ServiceLevel."""

    ref_doctype: str
    target: int

    async def validate(self) -> None:
        meta = await grunt.get_meta(self.ref_doctype)
        if meta is None:
            grunt.throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )
        dt = meta.doc
        if dt.is_child or dt.is_singleton or dt.is_virtual:
            grunt.throw(
                _("Service levels cannot track “%(doctype)s” documents") % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )
        if int(self.target or 0) < 1:
            grunt.throw(_("Time allowed must be at least 1"), "VALIDATION_ERROR")

        self.start_field = (self.get("start_field") or "").strip() or "created_at"
        self.due_field = (self.get("due_field") or "").strip() or None
        for label, field in (
            (_("Count from field"), self.start_field),
            (_("Deadline field"), self.due_field),
        ):
            if not field or field in _SYSTEM_DATES:
                continue
            fdef = meta.get_field(field)
            if fdef is None or fdef.fieldtype not in _DATE_TYPES:
                grunt.throw(
                    _("%(label)s: “%(field)s” is not a date field of %(doctype)s")
                    % {"label": label, "field": field, "doctype": dt.name},
                    "VALIDATION_ERROR",
                )
        if self.due_field in _SYSTEM_DATES:
            grunt.throw(_("The deadline field must be a field of the document"), "VALIDATION_ERROR")

        if (
            not (self.get("done_states") or "").strip()
            and not (self.get("done_condition") or "").strip()
        ):
            grunt.throw(
                _("Set done statuses or a done condition - otherwise the clock never stops"),
                "VALIDATION_ERROR",
            )
