"""Public logging API — grunt.log.

Usage in app controllers and hooks:
    from grunt.log import log

    log("employee.hired", employee_id=doc.name)
    log.debug("payroll.calculated", gross=42000, tax=6300)
    log.error("payment.failed", reason=str(e))
    log.exception("payment.crashed", order=order_id)  # includes traceback

    bound = log.bind(task="import_katottg")
    bound.info("import.started")  # every entry carries task=import_katottg

Logs are automatically routed to the appropriate file based on the calling
module (e.g. hrm.* → logs/apps/hrm/hrm.log, grunt.* → logs/system/grunt.log).
"""

from __future__ import annotations

import inspect

import structlog


def _caller_module(depth: int) -> str:
    """Return __name__ of the frame `depth` levels above this function."""
    stack = inspect.stack()
    if len(stack) <= depth:
        return "grunt"
    return stack[depth][0].f_globals.get("__name__", "grunt")


class _BaseLogger:
    """Shared level methods for the module-routing logger and its bound variant."""

    _bound: dict[str, object] = {}
    _module: str | None = None

    def __call__(self, event: str, **kwargs: object) -> None:
        self._emit("info", event, kwargs)

    def info(self, event: str, **kwargs: object) -> None:
        self._emit("info", event, kwargs)

    def error(self, event: str, **kwargs: object) -> None:
        self._emit("error", event, kwargs)

    def warning(self, event: str, **kwargs: object) -> None:
        self._emit("warning", event, kwargs)

    def debug(self, event: str, **kwargs: object) -> None:
        self._emit("debug", event, kwargs)

    def critical(self, event: str, **kwargs: object) -> None:
        self._emit("critical", event, kwargs)

    def exception(self, event: str, **kwargs: object) -> None:
        """Log at error level with the active exception's traceback attached."""
        self._emit("exception", event, kwargs)

    def bind(self, **kwargs: object) -> BoundLogger:
        """Return a logger that adds `kwargs` to every subsequent entry."""
        module = self._module or _caller_module(2)
        return BoundLogger(module, {**self._bound, **kwargs})

    def _emit(self, level: str, event: str, kwargs: dict[str, object]) -> None:
        # stack: _caller_module (0) → _emit (1) → level method (2) → caller (3)
        module = self._module or _caller_module(3)
        if self._bound:
            kwargs = {**self._bound, **kwargs}
        getattr(structlog.get_logger(module), level)(event, **kwargs)


class GruntLogger(_BaseLogger):
    """Callable logger that routes to the correct log file by caller module."""


class BoundLogger(_BaseLogger):
    """A GruntLogger with pinned context — module and bound kwargs fixed at bind()."""

    def __init__(self, module: str, bound: dict[str, object]) -> None:
        self._module = module
        self._bound = bound


log = GruntLogger()
