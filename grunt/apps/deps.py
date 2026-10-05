"""Python dependencies of the bench's apps.

An app declares its third-party packages in ``apps/<app>/pyproject.toml``.
They are not part of the framework's ``uv.lock`` (the framework can't know
which apps a bench has), so they are installed into the bench environment
separately - each app as an editable package, which pulls in its
dependencies (like ``bench setup requirements`` in Frappe).

Syncing the framework must therefore never prune packages outside its lock:
``uv sync --inexact`` (see ``mise.toml`` -> ``deps``), then ``grunt app deps``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def app_packages(apps_dir: Path, names: list[str] | None = None) -> list[Path]:
    """App directories that are Python packages (have a pyproject.toml)."""
    dirs = [
        d
        for d in sorted(apps_dir.iterdir())
        if d.is_dir() and d.name != "grunt" and (d / "pyproject.toml").exists()
    ]
    if names:
        dirs = [d for d in dirs if d.name in names]
    return dirs


def install_command(targets: list[Path]) -> list[str]:
    editable = [arg for d in targets for arg in ("-e", str(d))]
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install", "--python", sys.executable, *editable]
    return [sys.executable, "-m", "pip", "install", *editable]


def install_app_packages(apps_dir: Path, names: list[str] | None = None) -> list[str]:
    """Install the apps (editable) with their dependencies into this environment.

    Idempotent and quick when nothing changed. Returns the installed app names.
    """
    targets = app_packages(apps_dir, names)
    if targets:
        subprocess.run(install_command(targets), check=True)
    return [d.name for d in targets]
