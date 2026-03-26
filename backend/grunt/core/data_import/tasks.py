from __future__ import annotations

import structlog
from grunt.core.tasks.broker import task
from grunt.core.data_import.service import DataImportService
from grunt.core.site.manager import site_manager
from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()

# System user for data import tasks
SYSTEM_USER = GruntUser(
    email="system@grunt.local",
    full_name="System",
    is_superadmin=True
)

@task
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
