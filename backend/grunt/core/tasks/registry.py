from __future__ import annotations

import importlib
from pathlib import Path

import structlog

logger = structlog.get_logger()


def discover_tasks(apps_path: str | Path) -> None:
    """Search for task definitions in the given apps path."""
    apps_path = Path(apps_path)
    if not apps_path.exists():
        return

    for app_dir in apps_path.iterdir():
        if not app_dir.is_dir() or app_dir.name.startswith("."):
            continue

        # Look for tasks in {app}/tasks.py or {app}/tasks/*.py
        tasks_file = app_dir / "tasks.py"
        if tasks_file.exists():
            _load_module(f"grunt_apps.{app_dir.name}.tasks")

        tasks_dir = app_dir / "tasks"
        if tasks_dir.is_dir():
            for py_file in tasks_dir.glob("*.py"):
                if py_file.name == "__init__.py":
                    continue
                _load_module(f"grunt_apps.{app_dir.name}.tasks.{py_file.stem}")


def _load_module(module_name: str) -> None:
    try:
        importlib.import_module(module_name)
        logger.debug("tasks.module_loaded", module=module_name)
    except ImportError as e:
        logger.warning("tasks.load_failed", module=module_name, error=str(e))
