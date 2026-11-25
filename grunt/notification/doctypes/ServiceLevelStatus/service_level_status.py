"""Controller for the ``ServiceLevelStatus`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ServiceLevelStatus(Document):
    """DocType controller for ServiceLevelStatus."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str | None = None  # Document type
    ref_name: str | None = None  # Document
    service_level: str | None = None  # Service Level
    status: str | None = None  # Status
    due_at: datetime | None = None  # Deadline
    started_at: datetime | None = None  # Started
    met_at: datetime | None = None  # Done
    warned_at: datetime | None = None  # Warned
    breached_at: datetime | None = None  # Breached

    # end: auto-generated types
