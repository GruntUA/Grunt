"""``grunt release --deps``: the newest package versions within their major version.

The lock files are updated within the declared ranges (``uv lock --upgrade``,
``npm update --package-lock-only``); npm packages whose range lets nothing in (an
exact pin, ``^0.x``) get their newest minor in ``package.json``. Majors come from
Dependabot (``.github/dependabot.yml``), never with a release.
The commit goes through its own pull request into develop and the release waits for
its CI - a package that breaks the build never reaches master.
"""

import json
import os
import re
import shutil
import subprocess
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

import click

DEPS_TITLE = "build(deps): update packages within ranges"
# Workflow runs that do not fail the check (a skipped job, an informational one).
_PASSING = {"success", "skipped", "neutral"}


def locked_versions(tree: Path) -> dict[str, str]:
    """``{"name (python)": version, "name (npm)": version}`` from the lock files."""
    found: dict[str, str] = {}
    uv_lock = tree / "uv.lock"
    if uv_lock.is_file():
        for package in tomllib.loads(uv_lock.read_text()).get("package", []):
            if "version" in package:
                found[f"{package['name']} (python)"] = package["version"]
    npm_lock = tree / "package-lock.json"
    if npm_lock.is_file():
        for key, package in json.loads(npm_lock.read_text()).get("packages", {}).items():
            # Top-level packages only: nested copies are npm's business.
            name = key.removeprefix("node_modules/")
            nested = "/node_modules/" in name
            if key.startswith("node_modules/") and not nested and "version" in package:
                found[f"{name} (npm)"] = package["version"]
    return found


def version_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """``name old -> new`` for every package whose locked version changed."""
    lines = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old != new:
            lines.append(f"{name} {old or '(new)'} -> {new or '(removed)'}")
    return lines


def _tool(name: str, trusted_dir: Path) -> str | None:
    """The tool from the app's mise.toml (the throwaway worktree is not trusted by
    mise), else from PATH."""
    if shutil.which("mise"):
        found = subprocess.run(
            ["mise", "which", name], cwd=trusted_dir, capture_output=True, text=True, check=False
        )
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip()
    return shutil.which(name)


def _run(cmd: list[str], tree: Path, env: dict[str, str]) -> None:
    result = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-5:]
        raise click.ClickException(f"{' '.join(cmd[:3])} failed:\n" + "\n".join(tail))


def held_back(manifest: dict) -> list[str]:
    """npm packages whose range lets no minor version in: an exact pin (``1.1.414``)
    or a ``0.x`` caret / any tilde range (``^0.6.1``, ``~2.3.0``)."""
    held = []
    for section in ("dependencies", "devDependencies"):
        for name, spec in manifest.get(section, {}).items():
            if re.match(r"^(\d|\^0\.|~)", spec):
                held.append(name)
    return sorted(held)


def update_locks(tree: Path, trusted_dir: Path) -> list[str]:
    """Update the dependencies in ``tree`` within their major version: the lock
    files within the declared ranges, plus the :func:`held_back` packages raised
    to their newest minor in ``package.json``. The changed versions."""
    before = locked_versions(tree)
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    if (tree / "uv.lock").is_file():
        uv = _tool("uv", trusted_dir)
        if not uv:
            raise click.ClickException("uv is not installed")
        _run([uv, "lock", "--upgrade", "--quiet"], tree, env)
    if (tree / "package-lock.json").is_file():
        npm = _tool("npm", trusted_dir)
        if not npm:
            raise click.ClickException("npm is not installed")
        node_env = {**env, "PATH": f"{Path(npm).parent}{os.pathsep}{env.get('PATH', '')}"}
        # --prefer-online: a version published minutes ago is not in the cached
        # metadata yet, while a dependent's fresh metadata already asks for it (ETARGET).
        quiet = [
            "--package-lock-only",
            "--prefer-online",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ]
        held = held_back(json.loads((tree / "package.json").read_text()))
        if held:
            # Their ranges allow no update at all: the newest minor, as Dependabot
            # (.github/dependabot.yml) proposes majors only. --peer: no ERESOLVE.
            ncu = ["npx", "-y", "npm-check-updates", "--target", "minor", "--peer", "-u"]
            _run([*ncu, "--filter", ",".join(held)], tree, node_env)
            _run([npm, "install", *quiet], tree, node_env)
        _run([npm, "update", *quiet], tree, node_env)
    return version_changes(before, locked_versions(tree))


def deps_pr_body(changes: list[str]) -> str:
    listed = "\n".join(f"- {line}" for line in changes)
    return (
        "Within the major versions: `uv lock --upgrade` and `npm update` (lock files,"
        " within the declared ranges), exact pins and `0.x` ranges in `package.json`"
        " raised to their newest minor - opened by `grunt release --deps`, merged once"
        f" CI is green.\n\n{listed}\n"
    )


def wait_for_ci(
    repo: Path,
    sha: str,
    *,
    timeout: float = 45 * 60,
    interval: float = 20,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, list[str]]:
    """Wait for the workflow runs of ``sha``: ``(all passed, failed run names)``.

    A failed run ends the wait at once. Success needs two polls in a row with the
    same finished runs: GitHub creates the runs one by one, and a quick one (the PR
    title check) must not pass for the whole CI before CI's own run shows up."""
    deadline = time.monotonic() + timeout
    settled: list[str] | None = None
    while True:
        sleep(interval)
        result = subprocess.run(
            ["gh", "run", "list", "--commit", sha, "--json", "name,status,conclusion"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        runs = json.loads(result.stdout or "[]") if result.returncode == 0 else []
        failed = sorted(
            run["name"]
            for run in runs
            if run["status"] == "completed" and run["conclusion"] not in _PASSING
        )
        if failed:
            return False, failed
        finished = sorted(run["name"] for run in runs) if runs else None
        if finished and all(run["status"] == "completed" for run in runs):
            if finished == settled:
                return True, []
            settled = finished
        else:
            settled = None
        if time.monotonic() > deadline:
            return False, ["timed out waiting for CI"]
