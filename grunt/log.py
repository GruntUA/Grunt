"""Public logging API — grunt.log.

Usage in app controllers and hooks:
    import grunt

    grunt.log("employee.hired", employee_id=doc.name)
    grunt.log.debug("payroll.calculated", gross=42000, tax=6300)
    grunt.log.error("payment.failed", reason=str(e))

Logs are automatically routed to the appropriate file based on the calling
module (e.g. hrm.* → logs/apps/hrm/hrm.log, grunt.* → logs/system/grunt.log).
"""

from __future__ import annotations

import inspect

import structlog


class GruntLogger:
    """Callable logger that routes to the correct log file by caller module."""

    def __call__(self, event: str, **kwargs: object) -> None:
        self._log("info", event, **kwargs)

    def info(self, event: str, **kwargs: object) -> None:
        self._log("info", event, **kwargs)

    def error(self, event: str, **kwargs: object) -> None:
        self._log("error", event, **kwargs)

    def warning(self, event: str, **kwargs: object) -> None:
        self._log("warning", event, **kwargs)

    def debug(self, event: str, **kwargs: object) -> None:
        self._log("debug", event, **kwargs)

    def critical(self, event: str, **kwargs: object) -> None:
        self._log("critical", event, **kwargs)

    def _log(self, level: str, event: str, **kwargs: object) -> None:
        stack = inspect.stack()
        # stack depth: _log (0) → info/error/... (1) → caller (2)
        caller_module = (
            stack[2][0].f_globals.get("__name__", "grunt")
            if len(stack) > 2
            else "grunt"
        )
        getattr(structlog.get_logger(caller_module), level)(event, **kwargs)


log = GruntLogger()
