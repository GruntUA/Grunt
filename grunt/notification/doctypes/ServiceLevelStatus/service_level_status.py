"""Controller for the ``ServiceLevelStatus`` DocType."""

from datetime import datetime

from grunt.document.base import Document


class ServiceLevelStatus(Document):
    """DocType controller for ServiceLevelStatus."""

    ref_doctype: str | None
    ref_name: str | None
    service_level: str | None
    status: str | None
    due_at: datetime | None
    started_at: datetime | None
    met_at: datetime | None
    warned_at: datetime | None
    breached_at: datetime | None
