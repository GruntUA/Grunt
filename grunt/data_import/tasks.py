from __future__ import annotations

import structlog

from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.data_import.service import DataImportService
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task

logger = structlog.get_logger()


@retryable_task(max_retries=3, delay=60)
async def run_data_import(data_import_id: str):
    """Background task to execute a DataImport processing."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session:
        service = DataImportService(session, eng)

        try:
            logger.info("data_import.task_started", id=data_import_id)
            await service.run_import(data_import_id, SYSTEM_USER)
            logger.info("data_import.task_finished", id=data_import_id)
        except Exception as e:
            logger.error("data_import.task_failed", id=data_import_id, error=str(e))
            raise
