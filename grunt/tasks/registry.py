from __future__ import annotations

import importlib
from pathlib import Path

from grunt.log import log


def discover_tasks(apps_path: str | Path) -> None:
    """Search for task definitions in the given apps path.

    Expects ``apps_path`` to be the ``bench_dir/apps/`` directory.
    Tasks are imported as ``{app_name}.tasks`` or ``{app_name}.tasks.{module}``.
    """
    apps_path = Path(apps_path)
    if not apps_path.exists():
        return

    for app_dir in apps_path.iterdir():
        if not app_dir.is_dir() or app_dir.name.startswith((".", "_")):
            continue

        # Look for tasks in {app}/tasks.py or {app}/tasks/*.py
        tasks_file = app_dir / "tasks.py"
        if tasks_file.exists():
            _load_module(f"{app_dir.name}.tasks")

        tasks_dir = app_dir / "tasks"
        if tasks_dir.is_dir():
            for py_file in tasks_dir.glob("*.py"):
                if py_file.name == "__init__.py":
                    continue
                _load_module(f"{app_dir.name}.tasks.{py_file.stem}")


def _load_module(module_name: str) -> None:
    try:
        importlib.import_module(module_name)
        log.debug("tasks.module_loaded", module=module_name)
    except ImportError as e:
        log.warning("tasks.load_failed", module=module_name, error=str(e))
