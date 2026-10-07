"""Logging configuration - configures structlog with rotating file handlers.

Call configure_logging() once at application startup (in main.py lifespan).
After that, all structlog.get_logger(name) calls are routed automatically:

  grunt.web.<safe_site>         -> logs/web/<site>/access.log  (HTTP access)
  grunt.db.*                    -> logs/db/queries.log         (slow queries)
  grunt.tasks.*, grunt.worker.* -> logs/scheduler/tasks.log    (background)
  <app_name>.*                  -> logs/apps/<app>/            (per-app)
  grunt.*  (catch-all)          -> logs/system/grunt.log       (system)
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import re
import sysconfig
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

import structlog

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from structlog.typing import ExcInfo

_LOG_SUBDIRS = ("system", "web", "apps", "sites", "db", "scheduler")

# Loggers that write to the scheduler log file
_SCHEDULER_LOGGERS = ("grunt.tasks", "grunt.worker", "grunt.tasks.scheduler")

_SEP = "─" * 80

_console_handler: logging.Handler | None = None

# Frames from these roots are library code - the compact traceback skips them.
_LIBRARY_ROOTS = tuple(
    {p for p in (sysconfig.get_paths().get("purelib"), sysconfig.get_paths().get("stdlib")) if p}
)
_COMPACT_FRAMES = 6
_COMPACT_MESSAGE_CHARS = 600
_COMPACT_SQL_CHARS = 200
# apps/grunt/grunt/logging_config.py -> apps/: project frames print relative to it
_APPS_DIR = str(Path(__file__).resolve().parents[2]) + "/"


def _short_path(filename: str) -> str:
    _, sep, rest = filename.partition("site-packages/")
    if sep:
        return rest
    if filename.startswith(_APPS_DIR):
        return filename[len(_APPS_DIR) :]
    return filename


def _is_library_frame(filename: str) -> bool:
    return (
        filename.startswith(_LIBRARY_ROOTS)
        or "site-packages" in filename
        or filename.startswith("<")
    )


def _one_line(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit] + "…" if len(text) > limit else text


def _short_message(exc: BaseException) -> str:
    """``str(exc)`` on one line, capped. A SQLAlchemy DB error is shown as its
    driver message plus the start of the statement - its ``str()`` carries
    the whole statement and parameters."""
    orig, statement = getattr(exc, "orig", None), getattr(exc, "statement", None)
    if orig is not None and statement:
        return (
            f"{_one_line(orig, _COMPACT_MESSAGE_CHARS)}\n"
            f"  SQL: {_one_line(statement, _COMPACT_SQL_CHARS)}"
        )
    return _one_line(exc, _COMPACT_MESSAGE_CHARS)


def compact_exception_formatter(sio: TextIO, exc_info: ExcInfo) -> None:
    """Exception type and message plus the project's own frames (innermost
    last), and where in library code it was finally raised. The full
    traceback lands in logs/system/grunt.log (and ErrorLog for HTTP 500s)."""
    exc_type, exc, tb = exc_info
    frames = traceback.extract_tb(tb)
    own = [
        f
        for f in frames
        if not _is_library_frame(f.filename) and "call_next(" not in (f.line or "")
    ][-_COMPACT_FRAMES:]  # middleware pass-through frames say nothing

    sio.write("\n")
    for f in own:
        sio.write(f"  {_short_path(f.filename)}:{f.lineno} in {f.name}\n")
        if f.line:
            sio.write(f"    {f.line.strip()}\n")
    if frames and (not own or frames[-1] is not own[-1]):
        last = frames[-1]
        sio.write(f"  … raised in {_short_path(last.filename)}:{last.lineno} in {last.name}\n")
    name = getattr(exc_type, "__name__", str(exc_type))
    sio.write(f"{name}: {_short_message(exc) if exc is not None else ''}")


class _HandledExceptionFilter(logging.Filter):
    """Drop uvicorn's ``Exception in ASGI application`` for an exception the
    app's 500 handler already logged - Starlette's ServerErrorMiddleware
    re-raises it after sending the response, so it would print twice."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not getattr(exc, "__grunt_logged__", False)


def mark_logged(exc: BaseException) -> None:
    """Flag *exc* as already logged, see :class:`_HandledExceptionFilter`."""
    with contextlib.suppress(AttributeError, TypeError):
        exc.__grunt_logged__ = True  # type: ignore[attr-defined]


def _slow_query_renderer(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> str:
    """Human-readable formatter for slow query log entries."""
    ts = (event_dict.get("timestamp") or "")[:19].replace("T", " ")
    level = (event_dict.get("level") or "").upper()
    event = event_dict.get("event") or ""
    sql = (event_dict.get("sql") or "").strip()
    duration = event_dict.get("duration_ms", "")
    threshold = event_dict.get("threshold_ms", "")
    req_id = event_dict.get("request_id") or ""
    param_count = event_dict.get("param_count", "")

    # Extra fields (anything not handled above)
    _known = {
        "timestamp",
        "level",
        "logger",
        "event",
        "sql",
        "duration_ms",
        "threshold_ms",
        "request_id",
        "param_count",
    }
    extras = {k: v for k, v in event_dict.items() if k not in _known and v is not None}

    header = f"{ts}  {level}  {event}"
    if duration != "":
        header += f"    {duration}ms  (limit: {threshold}ms)"
    if param_count != "":
        header += f"  params={param_count}"
    if req_id:
        header += f"\nreq: {req_id}"
    if extras:
        header += "  " + "  ".join(f"{k}={v}" for k, v in extras.items())

    parts = [_SEP, header]
    if sql:
        parts.append("")
        parts.append(sql)
    parts.append("")
    return "\n".join(parts)


def configure_console_logging(
    log_level: str = "INFO", *, debug: bool = False, rich_tracebacks: bool = False
) -> int:
    """structlog + the console handler; returns the numeric level.

    Runs at ``grunt.log`` import (so lines logged while modules load already
    look like the rest and DEBUG noise stays hidden) and again from
    :func:`configure_logging` with the site settings - the second call
    replaces the first handler instead of adding another.
    """
    global _console_handler
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors - used by all loggers
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=shared_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Console output - always enabled. Tracebacks are compact by default: the
    # rich formatter prints a box per frame (hundreds of lines for one SQL
    # error), and with show_locals it also pretty-prints every local of every
    # frame - on a deep SQLAlchemy stack that alone took over a second per
    # logged exception. Locals are never printed; rich_tracebacks brings back
    # the boxed frames.
    exception_formatter = (
        structlog.dev.RichTracebackFormatter(show_locals=False, max_frames=30)
        if rich_tracebacks
        else compact_exception_formatter
    )
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(exception_formatter=exception_formatter),
        ],
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.DEBUG if debug else numeric_level)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else numeric_level)
    if _console_handler is not None:
        root.removeHandler(_console_handler)
    root.addHandler(console_handler)
    _console_handler = console_handler

    # Suppress verbose third-party libraries that spam at DEBUG level
    _noisy_loggers = (
        "aiosqlite",  # logs every SQLite operation
        "sqlalchemy.pool",  # logs every connection pool event
        "sqlalchemy.engine",  # logs raw SQL when echo=True
        "sqlalchemy.orm",
        "uvicorn.access",  # uvicorn request log (we log via middleware)
        "asyncio",
        "multipart",
        "python_multipart",
        "taskiq",
        "httpcore2",
        "httpx2",
        "apscheduler",  # job add/remove/wakeup spam
        "apscheduler.scheduler",
        "apscheduler.executors",
        "apscheduler.jobstores",
    )
    for _name in _noisy_loggers:
        logging.getLogger(_name).setLevel(logging.WARNING)

    uvicorn_error = logging.getLogger("uvicorn.error")
    for filter_cls in (_WebSocketHandshakeFilter, _HandledExceptionFilter):
        if not any(isinstance(f, filter_cls) for f in uvicorn_error.filters):
            uvicorn_error.addFilter(filter_cls())

    return numeric_level


class _WebSocketHandshakeFilter(logging.Filter):
    """Drop uvicorn's per-connection WebSocket lines (``"WebSocket /path"
    [accepted]``, ``connection open/closed/rejected``): behind a proxy they
    carry the proxy's address, not the client's - ``grunt.api.v1.ws`` logs
    connects and rejections with the real IP itself."""

    _MESSAGES = ("connection open", "connection closed", "connection rejected (%d %s)")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.msg if isinstance(record.msg, str) else ""
        return not (msg in self._MESSAGES or '"WebSocket %s"' in msg)


def configure_logging(
    bench_dir: Path,
    site_names: list[str],
    log_level: str = "INFO",
    log_to_file: bool = True,
    debug: bool = False,
    rich_tracebacks: bool = False,
) -> None:
    """Configure structlog with stdlib backend and optional file handlers.

    Always sets up console output (Rich in debug, plain JSON in production).
    File handlers are added when log_to_file=True.
    """
    log_dir = bench_dir / "logs"

    if log_to_file:
        _ensure_dirs(log_dir, site_names, bench_dir / "apps")

    numeric_level = configure_console_logging(
        log_level, debug=debug, rich_tracebacks=rich_tracebacks
    )

    if not log_to_file:
        return

    # JSON formatter for files - format_exc_info turns exc_info into the full
    # traceback text (without it the file only said "exc_info": true).
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )

    # System log - grunt root (catch-all for framework internals)
    _add_file_handler(
        "grunt",
        log_dir / "system" / "grunt.log",
        json_formatter,
        numeric_level,
        propagate=True,  # also goes to console via root
    )

    # Per-site HTTP access logs
    for site_name in site_names:
        safe = _safe_logger_name(site_name)
        _add_file_handler(
            f"grunt.web.{safe}",
            log_dir / "web" / site_name / "access.log",
            json_formatter,
            logging.INFO,
            propagate=False,
        )

    # DB log - human-readable format with SQL on its own lines
    db_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _slow_query_renderer,
        ],
    )
    _add_file_handler(
        "grunt.db",
        log_dir / "db" / "queries.log",
        db_formatter,
        numeric_level,
        propagate=False,
    )

    # Scheduler / worker logs
    for logger_name in _SCHEDULER_LOGGERS:
        _add_file_handler(
            logger_name,
            log_dir / "scheduler" / "tasks.log",
            json_formatter,
            numeric_level,
            propagate=False,
        )

    # Per-app logs (all apps under bench/apps/ except grunt itself)
    apps_dir = bench_dir / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if (
                app_dir.is_dir()
                and app_dir.name != "grunt"
                and not app_dir.name.startswith((".", "_"))
            ):
                app_name = app_dir.name
                _add_file_handler(
                    app_name,
                    log_dir / "apps" / app_name / f"{app_name}.log",
                    json_formatter,
                    numeric_level,
                    propagate=True,  # propagates to root for console output
                )


def _ensure_dirs(log_dir: Path, site_names: list[str], apps_dir: Path) -> None:
    for subdir in _LOG_SUBDIRS:
        (log_dir / subdir).mkdir(parents=True, exist_ok=True)
    for site_name in site_names:
        (log_dir / "web" / site_name).mkdir(parents=True, exist_ok=True)
        (log_dir / "sites" / site_name).mkdir(parents=True, exist_ok=True)
    if apps_dir.is_dir():
        for app_dir in apps_dir.iterdir():
            if app_dir.is_dir() and not app_dir.name.startswith((".", "_")):
                (log_dir / "apps" / app_dir.name).mkdir(parents=True, exist_ok=True)


def _add_file_handler(
    logger_name: str,
    log_path: Path,
    formatter: logging.Formatter,
    level: int,
    *,
    propagate: bool,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    std_logger = logging.getLogger(logger_name)
    std_logger.addHandler(handler)
    std_logger.setLevel(level)
    std_logger.propagate = propagate


def _safe_logger_name(site_name: str) -> str:
    """Replace dots and hyphens so site name doesn't create unintended logger hierarchy."""
    return site_name.replace(".", "_").replace("-", "_")
