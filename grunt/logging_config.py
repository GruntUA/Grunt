"""Logging configuration — configures structlog with rotating file handlers.

Call configure_logging() once at application startup (in main.py lifespan).
After that, all structlog.get_logger(name) calls are routed automatically:

  grunt.web.<safe_site>         → logs/web/<site>/access.log  (HTTP access)
  grunt.db.*                    → logs/db/queries.log         (slow queries)
  grunt.tasks.*, grunt.worker.* → logs/scheduler/tasks.log    (background)
  <app_name>.*                  → logs/apps/<app>/            (per-app)
  grunt.*  (catch-all)          → logs/system/grunt.log       (system)
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import structlog

_LOG_SUBDIRS = ("system", "web", "apps", "sites", "db", "scheduler")

# Loggers that write to the scheduler log file
_SCHEDULER_LOGGERS = ("grunt.tasks", "grunt.worker", "grunt.tasks.scheduler")


def configure_logging(
    bench_dir: Path,
    site_names: list[str],
    log_level: str = "INFO",
    log_to_file: bool = True,
    debug: bool = False,
) -> None:
    """Configure structlog with stdlib backend and optional file handlers.

    Always sets up console output (Rich in debug, plain JSON in production).
    File handlers are added when log_to_file=True.
    """
    log_dir = bench_dir / "logs"

    if log_to_file:
        _ensure_dirs(log_dir, site_names, bench_dir / "apps")

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors — used by all loggers
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

    # Console output — always enabled
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ],
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.DEBUG if debug else numeric_level)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else numeric_level)
    root.addHandler(console_handler)

    if not log_to_file:
        return

    # JSON formatter for files
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    # System log — grunt root (catch-all for framework internals)
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

    # DB log
    _add_file_handler(
        "grunt.db",
        log_dir / "db" / "queries.log",
        json_formatter,
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
                    propagate=False,
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
