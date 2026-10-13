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

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name


def app_packages(apps_dir: Path, names: list[str] | None = None) -> list[Path]:
    """App directories that are Python packages (have a pyproject.toml)."""
    if not apps_dir.is_dir():  # a framework checkout outside a bench (CI)
        return []
    dirs = [
        d
        for d in sorted(apps_dir.iterdir())
        if d.is_dir() and d.name != "grunt" and (d / "pyproject.toml").exists()
    ]
    if names:
        dirs = [d for d in dirs if d.name in names]
    return dirs


def _name(spec: str) -> str:
    return canonicalize_name(re.split(r"[\s\[<>=!~;@(]", spec.strip(), maxsplit=1)[0])


def app_only_requirements(apps: list[Path], lock_file: Path) -> list[str]:
    """Packages the apps declare that the framework's uv.lock doesn't pin -
    the only ones an upgrade of the apps' dependencies may move (the rest
    stays at the lock's versions)."""
    locked = set()
    if lock_file.exists():
        locked = {
            canonicalize_name(p["name"])
            for p in tomllib.loads(lock_file.read_text()).get("package", [])
        }
    app_names = {canonicalize_name(d.name) for d in apps}
    found: set[str] = set()
    for app in apps:
        project = tomllib.loads((app / "pyproject.toml").read_text()).get("project", {})
        found.update(_name(spec) for spec in project.get("dependencies", []))
    return sorted(found - locked - app_names)


def uv_binary() -> str | None:
    """uv the framework's mise.toml pins, else the one on PATH."""
    mise = shutil.which("mise") or str(Path.home() / ".local/bin/mise")
    if Path(mise).exists():
        framework = Path(__file__).resolve().parents[2]
        try:
            found = subprocess.run(
                [mise, "which", "uv"], cwd=framework, capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except OSError, subprocess.SubprocessError:
            found = ""
        if found:
            return found
    return shutil.which("uv")


def install_command(targets: list[Path], upgrade: list[str] | None = None) -> list[str]:
    editable = [arg for d in targets for arg in ("-e", str(d))]
    uv = uv_binary()
    if uv:
        flags = [arg for name in upgrade or [] for arg in ("--upgrade-package", name)]
        return [uv, "pip", "install", "--python", sys.executable, *flags, *editable]
    flags = ["--upgrade", "--upgrade-strategy", "only-if-needed", *(upgrade or [])]
    return [sys.executable, "-m", "pip", "install", *editable, *(flags if upgrade else [])]


def install_app_packages(
    apps_dir: Path, names: list[str] | None = None, upgrade: bool = False
) -> list[str]:
    """Install the apps (editable) with their dependencies into this environment.

    Idempotent and quick when nothing changed. *upgrade* also moves the
    packages only apps depend on to their newest versions (the framework's
    own stay at uv.lock). Returns the installed app names.
    """
    targets = app_packages(apps_dir, names)
    if targets:
        lock = apps_dir / "grunt" / "uv.lock"
        extra = app_only_requirements(targets, lock) if upgrade else None
        subprocess.run(install_command(targets, extra), check=True)
    return [d.name for d in targets]


_PLAN = re.compile(r"^ ([-+]) ([A-Za-z0-9_.-]+)==(\S+)$", re.M)


def app_updates(apps_dir: Path) -> list[str]:
    """``name old → new`` for what ``install_app_packages(upgrade=True)``
    would move (a dry run of the same install)."""
    targets = app_packages(apps_dir)
    names = app_only_requirements(targets, apps_dir / "grunt" / "uv.lock")
    cmd = install_command(targets, names)
    if not names or cmd[1:3] != ["pip", "install"]:
        return []  # pip has no dry-run plan to read
    result = subprocess.run(
        [*cmd[:3], "--dry-run", *cmd[3:]], capture_output=True, text=True, timeout=120
    )
    plan: dict[str, dict[str, str]] = {}
    for sign, name, version in _PLAN.findall(result.stdout + result.stderr):
        plan.setdefault(name, {})[sign] = version
    return [
        f"{name} {v['-']} → {v['+']}"
        for name, v in sorted(plan.items())
        if "-" in v and "+" in v and v["-"] != v["+"]
    ]
