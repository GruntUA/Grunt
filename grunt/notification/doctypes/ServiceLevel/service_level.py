"""ServiceLevel controller - validates an SLA policy against its DocType.

The tracking itself lives in :mod:`grunt.notification.sla`.
"""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry

_DATE_TYPES = ("Date", "Datetime")
_SYSTEM_DATES = ("created_at", "modified_at")


class ServiceLevel(Document):
    """DocType controller for ServiceLevel."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    ref_doctype: str  # Document type
    is_enabled: bool | None = None  # Enabled
    condition: str | None = None  # Applies when
    target: int  # Time allowed
    target_unit: str | None = None  # Unit
    start_field: str | None = None  # Count from field
    due_field: str | None = None  # Deadline field
    warn_before: int | None = None  # Warn hours before
    done_states: str | None = None  # Done statuses
    done_condition: str | None = None  # Or done when
    notify: str | None = None  # Notify
    escalate_to: str | None = None  # Escalate to
    channel: str | None = None  # Channel

    # end: auto-generated types

    async def validate(self) -> None:
        meta = await doctype_registry.get_meta(self.ref_doctype)
        if meta is None:
            throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )
        dt = meta.doc
        if dt.is_child or dt.is_singleton or not dt.has_table:
            throw(
                _("Service levels cannot track “%(doctype)s” documents") % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )
        if int(self.target or 0) < 1:
            throw(_("Time allowed must be at least 1"), "VALIDATION_ERROR")

        self.start_field = (self.start_field or "").strip() or "created_at"
        self.due_field = (self.due_field or "").strip() or None
        for label, field in (
            (_("Count from field"), self.start_field),
            (_("Deadline field"), self.due_field),
        ):
            if not field or field in _SYSTEM_DATES:
                continue
            fdef = meta.get_field(field)
            if fdef is None or fdef.fieldtype not in _DATE_TYPES:
                throw(
                    _("%(label)s: “%(field)s” is not a date field of %(doctype)s")
                    % {"label": label, "field": field, "doctype": dt.name},
                    "VALIDATION_ERROR",
                )
        if self.due_field in _SYSTEM_DATES:
            throw(_("The deadline field must be a field of the document"), "VALIDATION_ERROR")

        if not (self.done_states or "").strip() and not (self.done_condition or "").strip():
            throw(
                _("Set done statuses or a done condition - otherwise the clock never stops"),
                "VALIDATION_ERROR",
            )
