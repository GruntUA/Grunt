"""Notification controller - validates a rule: its rows, templates, event and dates."""

import ast

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.notification import rules
from grunt.notification.channels import get_channel
from grunt.notification.date_rules import DATE_EVENTS
from grunt.notification.events import get_event
from grunt.standard_records import mark_customized

_SYSTEM_DATES = ("created_at", "modified_at")


class Notification(Document):
    """DocType controller for Notification."""

    ref_doctype: str
    event: str
    condition: str | None
    subject_template: str | None
    message_template: str | None
    notify_actor: bool | None

    async def validate(self) -> None:
        mark_customized(self)
        await self._validate_rows()
        if self.event == "code":
            if get_event(self.get("event_key") or "") is None:
                throw(
                    _("Unknown code event “%(event)s”") % {"event": self.get("event_key")},
                    "VALIDATION_ERROR",
                )
            return
        if not self.get("ref_doctype"):
            throw(_("Choose the document type"), "VALIDATION_ERROR")
        if self.event not in DATE_EVENTS:
            return
        field = (self.get("date_field") or "").strip()
        self.date_field = field
        if int(self.get("days") or 0) < 0:
            throw(_("Days cannot be negative"), "VALIDATION_ERROR")
        if not field:
            throw(_("Choose the date field to count from"), "VALIDATION_ERROR")
        if field in _SYSTEM_DATES:
            return
        meta = await doctype_registry.get_meta(self.ref_doctype)
        fdef = meta.get_field(field) if meta else None
        if fdef is None or not fdef.is_date:
            throw(
                _("“%(field)s” is not a date field of %(doctype)s")
                % {"field": field, "doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )

    async def _validate_rows(self) -> None:
        """Recipients and channels present, channels known, templates and
        conditions well-formed - a typo is caught here, not when a document
        silently notifies nobody."""
        if not self.get("recipients"):
            throw(_("Add at least one recipient"), "VALIDATION_ERROR")
        if not self.get("channels"):
            throw(_("Add at least one channel"), "VALIDATION_ERROR")
        if self.get("event") != "code" and any(
            row.get("kind") == "Event recipients" for row in self.get("recipients") or []
        ):
            # Only code names them - on a document event the row would reach nobody.
            throw(
                _("“Event recipients” only work for a notification on a code event"),
                "VALIDATION_ERROR",
            )
        for row in self.get("channels") or []:
            if get_channel(row.get("channel") or "") is None:
                throw(
                    _("Unknown channel “%(channel)s”") % {"channel": row.get("channel")},
                    "VALIDATION_ERROR",
                )
        templates = [
            (_("Subject"), self.get("subject_template")),
            (_("Message"), self.get("message_template")),
        ]
        for row in self.get("channels") or []:
            templates += [(_("Subject"), row.get("subject")), (_("Message"), row.get("message"))]
        for label, template in templates:
            if template and (error := await rules.check_template(template)):
                throw(
                    _("%(field)s: template error - %(error)s") % {"field": label, "error": error},
                    "VALIDATION_ERROR",
                )
        conditions = [self.get("condition")] + [
            row.get("condition") for row in self.get("recipients") or []
        ]
        for condition in conditions:
            if condition and condition.strip():
                try:
                    ast.parse(condition.strip(), mode="eval")
                except SyntaxError as exc:
                    throw(
                        _("Condition “%(condition)s” is not a valid expression: %(error)s")
                        % {"condition": condition, "error": exc.msg},
                        "VALIDATION_ERROR",
                    )
