"""PreparedReport controller - a result goes with its file."""

from datetime import datetime

from grunt.document.base import Document
from grunt.local import require_session, system_context
lazy from grunt.document.api import documents


class PreparedReport(Document):
    """DocType controller for PreparedReport (see :mod:`grunt.reports.prepared`)."""

    report: str | None
    status: str | None
    filters: dict | None
    filters_hash: str | None
    started_at: datetime | None
    finished_at: datetime | None
    rows: int | None
    time_ms: int | None
    result_file: str | None
    error: str | None

    async def after_delete(self) -> None:
        if self.result_file:
            # The file is the system's, not the viewer's to delete.
            async with system_context(require_session()):
                await documents.delete_doc("File", self.result_file)
