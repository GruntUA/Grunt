from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from grunt.log import log

_ARGS_PREVIEW_MAX = 2000


class BackgroundTaskLoggingMiddleware(TaskiqMiddleware):
    """Records unrecoverable background-task failures to ``ErrorLog``.

    Successful runs are not persisted anywhere in the DB. Every task used to
    get a ``BackgroundTaskLog`` row on start (and an update on finish), which
    turned routine traffic — the 5-minute email-queue tick, a notification
    rule check on every matching document write, every ``enqueue_doc()``
    call — into permanent rows nobody read. Mirrors Frappe's model: ad-hoc
    ``frappe.enqueue`` jobs live transiently in Redis/RQ, and only unhandled
    errors ever reach the DB (their ``Error Log``).
    """

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
        will_retry, attempt, _, delay = self._retry_info(message)

        if will_retry:
            next_attempt = datetime.now(UTC) + timedelta(seconds=delay)
            log.info(
                "tasks.retry_scheduled",
                task=message.task_name,
                attempt=attempt,
                next_attempt=next_attempt.isoformat(),
            )
            return

        try:
            args_str = json.dumps({"args": message.args, "kwargs": message.kwargs}, default=str)
            if len(args_str) > _ARGS_PREVIEW_MAX:
                args_str = args_str[:_ARGS_PREVIEW_MAX] + "... [TRUNCATED]"
        except Exception:
            args_str = ""

        try:
            import grunt
            from grunt.monitoring.error_log import record_error
            from grunt.site.manager import site_manager

            site = site_manager.get_active_site()
            maker = site_manager.get_session_maker(site)
            eng = site_manager.get_engine(site)
            async with maker() as session, grunt.system_context(session, eng):
                await record_error(
                    exc=exception,
                    message=f"{exception}\n\nAttempt: {attempt}\nArguments: {args_str}",
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
