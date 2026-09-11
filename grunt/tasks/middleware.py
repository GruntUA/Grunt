from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from grunt.app import grunt
from grunt.log import log
from grunt.site.manager import site_manager


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
                async with grunt.system_context(session, eng):
                    args_str = json.dumps({"args": message.args, "kwargs": message.kwargs})
                    if len(args_str) > 5000:
                        args_str = args_str[:5000] + "... [TRUNCATED]"

                    result = await grunt.new_doc(
                        "BackgroundTaskLog",
                        {
                            "task_name": message.task_name,
                            "status": "Started",
                            "started_at": datetime.now(UTC).isoformat(),
                            "arguments": args_str,
                        },
                    )
                await session.commit()
                self.log_ids[message.task_id] = result["name"]

        except Exception as e:
            log.error("tasks.middleware.pre_execute_failed", error=str(e), task=message.task_name)

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
            async with maker() as session, grunt.system_context(session, eng):
                update_data: dict[str, Any] = {
                    "status": "Error" if result.is_err else "Success",
                    "finished_at": datetime.now(UTC),
                }
                if result.is_err:
                    update_data["error_message"] = str(result.error)
                await grunt.db.set_value("BackgroundTaskLog", log_id, update_data)
                await session.commit()

        except Exception as e:
            log.error("tasks.middleware.post_execute_failed", error=str(e), log_id=log_id)
        finally:
            self.log_ids.pop(message.task_id, None)

    def _retry_info(self, message: TaskiqMessage) -> tuple[bool, int, int, float]:
        """Return (will_retry, attempt_number, max_retries, delay_seconds) for this failure."""
        retry_on_error = message.labels.get("retry_on_error", False)
        if isinstance(retry_on_error, str):
            retry_on_error = retry_on_error.lower() == "true"

        attempt = int(message.labels.get("_retries", 0)) + 1
        max_retries = int(message.labels.get("max_retries", 3))
        delay = float(message.labels.get("delay", 60))

        will_retry = bool(retry_on_error) and attempt < max_retries
        return will_retry, attempt, max_retries, delay

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: BaseException
    ) -> None:
        """Called if an unhandled error occurs."""
        log_id = self.log_ids.get(message.task_id)
        if not log_id:
            return

        try:
            will_retry, attempt, _, delay = self._retry_info(message)

            update_data: dict[str, Any] = {
                "finished_at": datetime.now(UTC),
                "error_message": str(exception),
                "retry_count": attempt,
            }

            if will_retry:
                next_attempt = datetime.now(UTC) + timedelta(seconds=delay)
                update_data["status"] = "Retrying"
                update_data["next_attempt_at"] = next_attempt
                log.info(
                    "tasks.retry_scheduled",
                    task=message.task_name,
                    attempt=attempt,
                    next_attempt=next_attempt.isoformat(),
                )
            else:
                update_data["status"] = "Error"

            site = site_manager.get_active_site()
            maker = site_manager.get_session_maker(site)
            eng = site_manager.get_engine(site)
            async with maker() as session, grunt.system_context(session, eng):
                await grunt.db.set_value("BackgroundTaskLog", log_id, update_data)
                if not will_retry:
                    from grunt.monitoring.error_log import record_error

                    await record_error(
                        exc=exception,
                        context="Background Task",
                        method=message.task_name,
                        session=session,
                    )
                await session.commit()

        except Exception:
            log.error(
                "tasks.error_logging_failed",
                task_id=message.task_id,
                task=message.task_name,
                exc_info=True,
            )
        finally:
            self.log_ids.pop(message.task_id, None)
