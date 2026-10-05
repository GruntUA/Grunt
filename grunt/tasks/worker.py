"""Worker entry point: ``taskiq worker grunt.tasks.worker:broker``.

TaskIQ runs the worker in its own process and imports only the broker
module, so a task is unknown to the worker unless the module defining it was
imported - the web app gets those imports for free (routes, scheduler,
hooks), the worker does not. Here every module that declares a task
(``@task`` / ``@retryable_task`` at the top level) is imported: the
framework's own and each app's under ``bench/apps/<app>/<app>/``.

On start the worker boots like the web server (``grunt.startup.lifespan.boot``:
sites, DocType registry, installed apps' hooks) - minus the scheduler, which
runs in the web process and only enqueues.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

from taskiq import TaskiqEvents, TaskiqState

from grunt import log
from grunt.db.write_intent import set_process_default
from grunt.tasks.broker import broker

__all__ = ["broker", "import_task_modules"]

_TASK_DECORATOR = re.compile(r"^@(?:retryable_task|task|broker\.task)\b", re.MULTILINE)
_SKIP_DIRS = {"tests", "__pycache__", "node_modules", "migrations"}


def _task_modules(package_dir: Path) -> list[str]:
    """Dotted names of the modules under *package_dir* that declare a task."""
    root = package_dir.parent
    found = []
    for path in sorted(package_dir.rglob("*.py")):
        rel = path.relative_to(root)
        if _SKIP_DIRS & set(rel.parts) or path.name.startswith("test_"):
            continue
        try:
            if _TASK_DECORATOR.search(path.read_text(encoding="utf-8")):
                found.append(".".join(rel.with_suffix("").parts))
        except OSError, UnicodeDecodeError:
            continue
    return found


def import_task_modules(apps_dir: Path | None = None) -> list[str]:
    """Import every task-declaring module of the framework and the bench's apps."""
    import grunt

    packages = [Path(grunt.__file__).parent]
    if apps_dir is not None and apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            package = app_dir / app_dir.name
            if app_dir.name == "grunt" or not (package / "__init__.py").exists():
                continue
            if str(app_dir) not in sys.path:
                sys.path.insert(0, str(app_dir))
            packages.append(package)

    loaded = []
    for package in packages:
        for name in _task_modules(package):
            try:
                importlib.import_module(name)
                loaded.append(name)
            except Exception as e:  # noqa: BLE001 - one broken app must not stop the worker
                log.warning("worker.task_module_failed", module=name, error=str(e))
    log.info("worker.tasks_registered", modules=len(loaded), tasks=len(broker.get_all_tasks()))
    return loaded


def _apps_dir() -> Path | None:
    from grunt.site.manager import site_manager

    return site_manager.bench_dir / "apps"


import_task_modules(_apps_dir())

# Tasks write - on SQLite take the write lock at BEGIN (grunt/db/write_intent.py).
set_process_default(True)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _boot_worker(state: TaskiqState) -> None:
    from grunt.startup.lifespan import boot

    await boot()
