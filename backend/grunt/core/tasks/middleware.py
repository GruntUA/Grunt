from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog
from taskiq import TaskiqMiddleware, TaskiqMessage, TaskiqResult

from grunt.core.site.manager import site_manager
from grunt.core.document.service import DocumentService
from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()

# System user for background tasks
SYSTEM_USER = GruntUser(
    email="system@grunt.local",
    full_name="System",
    is_superadmin=True
)

class BackgroundTaskLoggingMiddleware(TaskiqMiddleware):
    """Middleware to log TaskIQ task execution to BackgroundTaskLog DocType."""

    def __init__(self) -> None:
        super().__init__()
        self.log_ids: dict[str, str] = {}

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Called before task execution in the worker."""
        try:
            site = site_manager.get_active_site()
            maker = site_manager.get_session_maker(site)
            eng = site_manager.get_engine(site)
            async with maker() as session:
                service = DocumentService(session, eng)
                
                # Create a log entry with "Started" status
                log_data = {
                    "task_name": message.task_name,
                    "status": "Started",
                    "started_at": datetime.now().isoformat(),
                    "arguments": json.dumps({
                        "args": message.args,
                        "kwargs": message.kwargs
                    })
                }
                
                result = await service.create_document(
                    "BackgroundTaskLog", 
                    log_data, 
                    SYSTEM_USER
                )
                await session.commit()
                self.log_ids[message.task_id] = result["id"]
                
        except Exception as e:
            logger.error("tasks.middleware.pre_execute_failed", error=str(e), task=message.task_name)
            
        return message

    async def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        """Called after task execution."""
        log_id = self.log_ids.get(message.task_id)
        if not log_id:
            return

        try:
            site = site_manager.get_active_site()
            maker = site_manager.get_session_maker(site)
            eng = site_manager.get_engine(site)
            async with maker() as session:
                service = DocumentService(session, eng)
                
                update_data = {
                    "status": "Error" if result.is_err else "Success",
                    "finished_at": datetime.now().isoformat(),
                }
                
                if result.is_err:
                    update_data["error_message"] = str(result.error)
                
                await service.update_document(
                    "BackgroundTaskLog",
                    log_id,
                    update_data,
                    SYSTEM_USER
                )
                await session.commit()
                
        except Exception as e:
            logger.error("tasks.middleware.post_execute_failed", error=str(e), log_id=log_id)
        finally:
            self.log_ids.pop(message.task_id, None)

    async def on_error(
        self, 
        message: TaskiqMessage, 
        result: TaskiqResult[Any], 
        exception: Exception
    ) -> None:
        """Called if an unhandled error occurs."""
        log_id = self.log_ids.get(message.task_id)
        if not log_id:
            return

        try:
            site = site_manager.get_active_site()
            maker = site_manager.get_session_maker(site)
            eng = site_manager.get_engine(site)
            async with maker() as session:
                service = DocumentService(session, eng)
                await service.update_document(
                    "BackgroundTaskLog",
                    log_id,
                    {
                        "status": "Error",
                        "finished_at": datetime.now().isoformat(),
                        "error_message": str(exception)
                    },
                    SYSTEM_USER
                )
                await session.commit()
        except Exception:
            pass
        finally:
            self.log_ids.pop(message.task_id, None)
