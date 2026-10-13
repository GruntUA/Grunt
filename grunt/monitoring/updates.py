"""Available updates - the «Оновлення» rows of the health report.

What runs here next to the newest release of it: the framework and every app
(git: a newer release tag, or new commits on the branch), Python, Node.js,
rclone, uv and mise, and the Python / npm packages. ``grunt update`` installs
all of it; packages beyond the committed lock files arrive with the next
framework release (in development: ``grunt update --upgrade-packages``).

Answers come from the network (git remotes, endoflife.date, PyPI, npm), so
every one is cached for a few hours per process, and a source that can't be
reached gives an ``Info`` row instead of failing the report.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import platform
import re
import shutil
import time
import tomllib
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.version import InvalidVersion, Version

import grunt
from grunt import log
from grunt.config import settings
from grunt.i18n import _
from grunt.monitoring.health import ERROR, INFO, OK, WARNING, Row, row
from grunt.site.manager import site_manager
from grunt.version import FRAMEWORK_DIR, app_version

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

CACHE_TTL = 6 * 3600
CACHE_TTL_FAILED = 30 * 60
TIMEOUT = 20.0
LIST_MAX = 8

_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_cache: dict[str, tuple[float, Any]] = {}


class UnavailableError(Exception):
    """The newest version could not be found out - not a problem of the site."""


async def cached(key: str, fn: Callable[[], Awaitable[Any]]) -> Any:
    """``fn()`` remembered for CACHE_TTL; an UnavailableError for CACHE_TTL_FAILED."""
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        if isinstance(hit[1], UnavailableError):
            raise hit[1]
        return hit[1]
    try:
        value = await fn()
    except UnavailableError as e:
        _cache[key] = (time.monotonic() + CACHE_TTL_FAILED, e)
        raise
    _cache[key] = (time.monotonic() + CACHE_TTL, value)
    return value


def clear_cache() -> None:
    _cache.clear()


# Helpers


def tool(name: str) -> str | None:
    """A command-line tool, also where the services' short PATH doesn't look
    (``~/.local/bin``, mise shims)."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in (
        Path.home() / ".local/bin" / name,
        Path.home() / ".local/share/mise/shims" / name,
        Path.home() / ".cargo/bin" / name,
    ):
        if os.access(candidate, os.X_OK):
            return str(candidate)
    return None


async def run(*cmd: str, cwd: Path | None = None, timeout: float = TIMEOUT) -> str:
    """stdout of ``cmd``; UnavailableError when it can't run or fails."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if mise := tool("mise"):
        # mise shims (node, npm) need mise itself on PATH
        env["PATH"] = f"{Path(mise).parent}:{env.get('PATH', '')}"
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise UnavailableError(str(e)) from e
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise UnavailableError(_("timed out")) from e
    # npm outdated exits 1 when something is outdated - its JSON is still the answer
    if proc.returncode and not out.strip():
        lines = (err or out).decode(errors="replace").strip().splitlines()
        raise UnavailableError(lines[-1] if lines else f"exit {proc.returncode}")
    return out.decode(errors="replace")


async def fetch(url: str) -> str:
    import httpx2

    try:
        async with httpx2.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            return (await client.get(url)).raise_for_status().text
    except httpx2.HTTPError as e:
        raise UnavailableError(str(e)) from e


def newer(current: str, latest: str) -> bool:
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return False


def first_version(text: str) -> str:
    """The first ``1.2.3``-looking number in ``text``."""
    m = re.search(r"\d+\.\d+(?:\.\d+)?", text)
    if not m:
        raise UnavailableError(text.strip()[:100])
    return m.group(0)


def short_list(names: list[str]) -> str:
    text = ", ".join(names[:LIST_MAX])
    if len(names) > LIST_MAX:
        text += " " + _("and %(count)s more") % {"count": len(names) - LIST_MAX}
    return text


# Framework and apps (git)


def _git_dirs() -> list[tuple[str, Path]]:
    apps_dir = site_manager.bench_dir / "apps"
    dirs = [("grunt", FRAMEWORK_DIR)]
    for app in sorted(apps_dir.iterdir() if apps_dir.is_dir() else []):
        if app.name != "grunt" and (app / "app.json").exists() and (app / ".git").exists():
            dirs.append((app.name, app))
    return dirs


def _release_key(tag: str) -> tuple[int, ...] | None:
    m = _RELEASE_TAG.match(tag)
    return tuple(int(n) for n in m.groups()) if m else None


_NO_ACCESS = ("could not read username", "authentication failed", "repository exists", "not found")


async def ls_remote(path: Path, *args: str) -> str:
    try:
        return await run("git", "-C", str(path), "ls-remote", *args)
    except UnavailableError as e:
        if any(marker in str(e).lower() for marker in _NO_ACCESS):
            raise UnavailableError(
                _("no access to the repository - run `grunt update` in a terminal to add a token")
            ) from e
        raise


async def repo_update(path: Path) -> str | None:
    """What ``grunt update`` would bring to the checkout at *path*: the newer
    release tag (on a tag) or ``origin/<branch>`` (on a branch); None when
    up to date."""
    git = ("git", "-C", str(path))
    branch = (await run(*git, "rev-parse", "--abbrev-ref", "HEAD")).strip()
    if branch == "HEAD":  # detached - on a release tag
        here = [
            t for t in (await run(*git, "tag", "--points-at", "HEAD")).split() if _release_key(t)
        ]
        out = await ls_remote(path, "--tags", "--refs", "origin", "v*")
        remote = [r.rsplit("/", 1)[-1] for r in out.split() if r.startswith("refs/tags/")]
        releases = sorted((t for t in remote if _release_key(t)), key=_release_key)
        if not here or not releases:
            return None
        return releases[-1] if _release_key(releases[-1]) > _release_key(here[0]) else None
    out = await ls_remote(path, "origin", f"refs/heads/{branch}")
    if not out.strip():
        return None
    remote_sha = out.split()[0]
    head = (await run(*git, "rev-parse", "HEAD")).strip()
    if remote_sha == head:
        return None
    try:  # origin's head already in our history - we are ahead, not behind
        await run(*git, "merge-base", "--is-ancestor", remote_sha, "HEAD")
        return None
    except UnavailableError:
        return f"origin/{branch}"


async def code_rows(cat: str) -> list[Row]:
    async def one(name: str, path: Path) -> Row:
        current = grunt.__version__ if name == "grunt" else app_version(path)
        try:
            target = await cached(f"git:{path}", lambda: repo_update(path))
        except UnavailableError as e:
            return _unavailable(cat, name, current, e)
        if target:
            return _update_row(cat, name, current, target)
        return row(cat, name, OK, current)

    return list(await asyncio.gather(*(one(n, p) for n, p in _git_dirs())))


# Runtimes and tools


async def _cycles(product: str) -> list[dict[str, Any]]:
    return json.loads(await fetch(f"https://endoflife.date/api/{product}.json"))


async def runtime_row(cat: str, name: str, product: str, current: str) -> Row:
    """*current* against the newest patch of its release line, the line's end
    of life and the newest line (endoflife.date)."""
    try:
        cycles = await cached(f"eol:{product}", lambda: _cycles(product))
    except UnavailableError as e:
        return _unavailable(cat, name, current, e)
    v = Version(current)
    line = f"{v.major}.{v.minor}" if product == "python" else str(v.major)
    cycle = next((c for c in cycles if str(c.get("cycle")) == line), None)
    newest = str(cycles[0].get("cycle")) if cycles else line
    notes = []
    if newest != line and newer(line, newest):
        notes.append(_("%(name)s %(version)s is out.") % {"name": name, "version": newest})
    if cycle is None:
        return row(cat, name, INFO, current, " ".join(notes))
    eol = cycle.get("eol")
    if isinstance(eol, str) and date.fromisoformat(eol) <= date.today():
        return row(
            cat,
            name,
            ERROR,
            current,
            " ".join([_("No longer supported since %(date)s.") % {"date": eol}, *notes]),
        )
    latest = str(cycle.get("latest") or "")
    if latest and newer(current, latest):
        return _update_row(cat, name, current, latest, " ".join(notes))
    return row(cat, name, OK if not notes else INFO, current, " ".join(notes))


async def node_version() -> str:
    node = tool("node")
    if not node:
        raise UnavailableError(_("not installed"))
    return (await run(node, "--version", cwd=FRAMEWORK_DIR)).strip().lstrip("v")


async def tool_row(
    cat: str, name: str, current: Callable[[], Awaitable[str]], latest: Callable[[], Awaitable[str]]
) -> Row | None:
    """*name* against its newest release; None when it is not installed."""
    try:
        have = await current()
    except UnavailableError:
        return None
    try:
        newest = await cached(f"latest:{name}", latest)
    except UnavailableError as e:
        return _unavailable(cat, name, have, e)
    if newer(have, newest):
        return _update_row(cat, name, have, newest)
    return row(cat, name, OK, have)


async def tool_rows(cat: str) -> list[Row]:
    from grunt.storage.cloud.rclone import DOWNLOAD_URL, is_installed

    async def version_of(binary: str | None, *args: str) -> str:
        if not binary:
            raise UnavailableError(_("not installed"))
        return first_version(await run(binary, *args, cwd=FRAMEWORK_DIR))

    async def rclone_version() -> str:
        from grunt.storage.cloud.rclone import binary

        if not is_installed():
            raise UnavailableError(_("not installed"))
        return await version_of(binary(), "version")

    async def rclone_latest() -> str:
        return first_version(await fetch(f"{DOWNLOAD_URL}/version.txt"))

    async def uv_latest() -> str:
        return json.loads(await fetch("https://pypi.org/pypi/uv/json"))["info"]["version"]

    async def mise_latest() -> str:
        return first_version(await fetch("https://mise.jdx.dev/VERSION"))

    rows = await asyncio.gather(
        tool_row(cat, "rclone", rclone_version, rclone_latest),
        tool_row(cat, "uv", lambda: version_of(tool("uv"), "--version"), uv_latest),
        tool_row(cat, "mise", lambda: version_of(tool("mise"), "--version"), mise_latest),
    )
    return [r for r in rows if r]


# Packages


def lock_mismatches() -> list[str]:
    """Installed packages whose version differs from the framework's uv.lock."""
    lock_file = FRAMEWORK_DIR / "uv.lock"
    if not lock_file.exists():
        return []
    wrong = []
    for pkg in tomllib.loads(lock_file.read_text()).get("package", []):
        if "registry" not in pkg.get("source", {}):
            continue  # the framework / apps themselves (editable, virtual)
        try:
            installed = importlib.metadata.version(pkg["name"])
        except importlib.metadata.PackageNotFoundError:
            continue  # another platform's or an extra's package
        if Version(installed) != Version(pkg["version"]):
            wrong.append(f"{pkg['name']} {installed} → {pkg['version']}")
    return wrong


async def pypi_outdated() -> list[str]:
    uv = tool("uv")
    if not uv:
        raise UnavailableError(_("uv is not installed"))
    import sys

    out = await run(
        uv, "pip", "list", "--outdated", "--format", "json", "--python", sys.executable, timeout=60
    )
    return [
        f"{p['name']} {p['version']} → {p['latest_version']}"
        for p in json.loads(out or "[]")
        if not p.get("editable_project_location")
    ]


async def npm_outdated() -> list[str]:
    npm = tool("npm")
    if not npm or not (FRAMEWORK_DIR / "node_modules").is_dir():
        raise UnavailableError(_("not installed"))
    out = await run(npm, "outdated", "--json", cwd=FRAMEWORK_DIR, timeout=60)
    return [
        f"{name} {info.get('current')} → {info.get('latest')}"
        for name, info in json.loads(out or "{}").items()
        if info.get("current") and info.get("current") != info.get("latest")
    ]


async def package_rows(cat: str) -> list[Row]:
    rows = []
    wrong = await asyncio.to_thread(lock_mismatches)
    if wrong:
        rows.append(
            row(
                cat,
                _("Python packages"),
                WARNING,
                _("%(count)s differ from uv.lock") % {"count": len(wrong)},
                _("Run `grunt update`.") + " " + short_list(wrong),
            )
        )
    hint = (
        _("Update the lock files: `grunt update --upgrade-packages`, then commit them.")
        if settings.debug
        else _("Newer versions arrive with the next framework release.")
    )
    for name, key, fn, ok in (
        (_("Python packages"), "pypi", pypi_outdated, not wrong),
        (_("npm packages"), "npm", npm_outdated, True),
    ):
        try:
            outdated = await cached(f"outdated:{key}", fn)
        except UnavailableError as e:
            rows.append(_unavailable(cat, name, "", e))
            continue
        if outdated:
            rows.append(
                row(
                    cat,
                    name,
                    INFO,
                    _("%(count)s newer versions") % {"count": len(outdated)},
                    hint + " " + short_list(outdated),
                )
            )
        elif ok:
            rows.append(row(cat, name, OK, _("up to date")))
    return rows


# Rows


def _update_row(cat: str, name: str, current: str, target: str, note: str = "") -> Row:
    hint = _("Update available: %(target)s. Run `grunt update`.") % {"target": target}
    return row(cat, name, WARNING, f"{current} → {target}", f"{hint} {note}".strip())


def _unavailable(cat: str, name: str, current: str, e: Exception) -> Row:
    log.info("health.update_check_failed", check=name, error=str(e))
    return row(cat, name, INFO, current, _("Could not check for updates: %(error)s") % {"error": e})


async def check_updates() -> list[Row]:
    cat = _("Updates")

    async def runtimes() -> list[Row]:
        rows = [await runtime_row(cat, "Python", "python", platform.python_version())]
        try:
            node = await node_version()
        except UnavailableError:
            return rows
        return [*rows, await runtime_row(cat, "Node.js", "nodejs", node)]

    code, rts, tools, packages = await asyncio.gather(
        code_rows(cat), runtimes(), tool_rows(cat), package_rows(cat)
    )
    return [*code, *rts, *tools, *packages]
