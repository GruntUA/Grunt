from __future__ import annotations

import structlog

from grunt.core.data_import.tasks import run_data_import
from grunt.core.document.base import Document

logger = structlog.get_logger()

class DataImport(Document):
    """Controller for DataImport DocType."""

    async def after_insert(self) -> None:
        """Trigger the import task after the document is created."""
        if self.data.get("status") == "Pending":
            logger.info("data_import.triggering_task", id=self.data["id"])
            await run_data_import.kiq(self.data["id"])
