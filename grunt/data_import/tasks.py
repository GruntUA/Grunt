from __future__ import annotations

from grunt import log
from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.data_import.service import DataImportService
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task


@retryable_task(max_retries=3, delay=60)
async def run_data_import(data_import_id: str):
    """Background task to execute a DataImport processing."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session:
        service = DataImportService(session, eng)

        try:
            log.info("data_import.task_started", id=data_import_id)
            await service.run_import(data_import_id, SYSTEM_USER)
            log.info("data_import.task_finished", id=data_import_id)
        except Exception as e:
            log.error("data_import.task_failed", id=data_import_id, error=str(e))
            raise
