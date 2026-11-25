"""Notification controller - validates a rule: its rows, templates, event and dates."""

import ast

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.notification import rules
from grunt.notification.channels import get_channel
from grunt.notification.date_rules import DATE_EVENTS, MINUTE_EVENTS
from grunt.notification.events import get_event
from grunt.standard_records import mark_customized

_SYSTEM_DATES = ("created_at", "modified_at")
# Recipient kind -> the field naming whom it means.
_RECIPIENT_TARGET = {
    "Role": "role",
    "User group": "user_group",
    "User": "user",
    "Document field": "field",
    "Email": "email",
}


class Notification(Document):
    """DocType controller for Notification."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str | None = None  # Document type
    event: str  # Event
    event_key: str | None = None  # Code event
    workflow_actions: str | None = None  # Workflow actions
    date_field: str | None = None  # Date field
    days: int | None = None  # Days
    minutes: int | None = None  # Minutes
    every_year: bool | None = None  # Every year
    condition: str | None = None  # Condition
    notify_actor: bool | None = None  # Also notify who did it
    subject_template: str | None = None  # Subject
    message_template: str | None = None  # Message
    attach_print: bool | None = None  # Attach the document as PDF
    print_format: str | None = None  # Print format
    attach_files: bool | None = None  # Attach the document's files
    email_account: str | None = None  # Send from
    set_field: str | None = None  # Set field
    set_value: str | None = None  # To value
    is_enabled: bool | None = None  # Active
    is_mandatory: bool | None = None  # Mandatory
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App
    is_customized: bool | None = None  # Changed on this site
    recipients: list[dict]  # Table: NotificationRecipient
    channels: list[dict]  # Table: NotificationChannel

    # end: auto-generated types

    async def _validate_set_field(self) -> None:
        """The "after sending" field must be a field of the document."""
        field = (self.set_field or "").strip()
        self.set_field = field or None
        if not field or not self.ref_doctype:
            return
        meta = await doctype_registry.get_meta(self.ref_doctype)
        if meta is None or meta.get_field(field) is None:
            throw(
                _("“%(field)s” is not a field of %(doctype)s")
                % {"field": field, "doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )

    async def _validate_minutes(self) -> None:
        """A minutes-before/after rule counts from a date-and-time field."""
        field = (self.date_field or "").strip()
        self.date_field = field
        if int(self.minutes or 0) < 0:
            throw(_("Minutes cannot be negative"), "VALIDATION_ERROR")
        if not field:
            throw(_("Choose the date field to count from"), "VALIDATION_ERROR")
        if field in _SYSTEM_DATES:
            return
        meta = await doctype_registry.get_meta(self.ref_doctype)
        fdef = meta.get_field(field) if meta else None
        if fdef is None or fdef.fieldtype != "Datetime":
            throw(
                _("“%(field)s” is not a date-and-time field of %(doctype)s")
                % {"field": field, "doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )

    async def validate(self) -> None:
        mark_customized(self)
        await self._validate_rows()
        await self._validate_set_field()
        if self.event == "code":
            if get_event(self.event_key or "") is None:
                throw(
                    _("Unknown code event “%(event)s”") % {"event": self.event_key},
                    "VALIDATION_ERROR",
                )
            return
        if not self.ref_doctype:
            throw(_("Choose the document type"), "VALIDATION_ERROR")
        if self.event in MINUTE_EVENTS:
            await self._validate_minutes()
            return
        if self.event not in DATE_EVENTS:
            return
        field = (self.date_field or "").strip()
        self.date_field = field
        if int(self.days or 0) < 0:
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
        if not self.recipients:
            throw(_("Add at least one recipient"), "VALIDATION_ERROR")
        if not self.channels:
            throw(_("Add at least one channel"), "VALIDATION_ERROR")
        for row in self.recipients or []:
            # ``mandatory_depends_on`` holds in the form only - a row without
            # its target would silently notify nobody.
            field = _RECIPIENT_TARGET.get(row.get("kind") or "")
            if field and not str(row.get(field) or "").strip():
                throw(
                    _("Recipient “%(kind)s”: choose whom it means") % {"kind": _(row["kind"])},
                    "VALIDATION_ERROR",
                )
        if self.event != "code" and any(
            row.get("kind") == "Event recipients" for row in self.recipients or []
        ):
            # Only code names them - on a document event the row would reach nobody.
            throw(
                _("“Event recipients” only work for a notification on a code event"),
                "VALIDATION_ERROR",
            )
        for row in self.channels or []:
            if get_channel(row.get("channel") or "") is None:
                throw(
                    _("Unknown channel “%(channel)s”") % {"channel": row.get("channel")},
                    "VALIDATION_ERROR",
                )
            if row.get("channel") == "webhook" and not row.get("webhook"):
                throw(_("Choose the webhook for the Webhook channel"), "VALIDATION_ERROR")
        templates = [
            (_("Subject"), self.subject_template),
            (_("Message"), self.message_template),
        ]
        for row in self.channels or []:
            templates += [(_("Subject"), row.get("subject")), (_("Message"), row.get("message"))]
        for label, template in templates:
            if template and (error := await rules.check_template(template)):
                throw(
                    _("%(field)s: template error - %(error)s") % {"field": label, "error": error},
                    "VALIDATION_ERROR",
                )
        conditions = [self.condition] + [row.get("condition") for row in self.recipients or []]
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
