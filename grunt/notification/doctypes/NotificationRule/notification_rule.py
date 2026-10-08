"""NotificationRule controller - checks date-based rules against their DocType."""

from __future__ import annotations

import grunt
from grunt import _
from grunt.document.base import Document
from grunt.notification.date_rules import DATE_EVENTS

_SYSTEM_DATES = ("created_at", "modified_at")


class NotificationRule(Document):
    """DocType controller for NotificationRule."""

    ref_doctype: str
    event: str

    async def validate(self) -> None:
        if self.event not in DATE_EVENTS:
            return
        field = (self.get("date_field") or "").strip()
        self.date_field = field
        if int(self.get("days") or 0) < 0:
            grunt.throw(_("Days cannot be negative"), "VALIDATION_ERROR")
        if not field:
            grunt.throw(_("Choose the date field to count from"), "VALIDATION_ERROR")
        if field in _SYSTEM_DATES:
            return
        meta = await grunt.get_meta(self.ref_doctype)
        fdef = meta.get_field(field) if meta else None
        if fdef is None or fdef.fieldtype not in ("Date", "Datetime"):
            grunt.throw(
                _("“%(field)s” is not a date field of %(doctype)s")
                % {"field": field, "doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )
