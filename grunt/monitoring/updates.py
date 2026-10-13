"""Available updates - the «Оновлення» rows of the health report.

What runs here next to the newest release of it: the framework and every app
(git: a newer release tag, or new commits on the branch), Python, Node.js,
rclone, uv and mise, and the Python / npm packages. ``grunt update`` installs
all of it; packages beyond the committed lock files arrive with the next
framework release (in development ``grunt update`` offers to update the lock
files).

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
import subprocess
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
    """A command-line tool: the version the framework's mise.toml pins (what
    ``grunt update`` upgrades - the server's own PATH may still point at the
    old one), else PATH, else where the services' short PATH doesn't look."""
    mise = shutil.which("mise") or str(Path.home() / ".local/bin/mise")
    if name != "mise" and os.access(mise, os.X_OK):
        try:
            found = subprocess.run(
                [mise, "which", name],
                cwd=FRAMEWORK_DIR,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        except OSError, subprocess.SubprocessError:
            found = ""
        if found and os.access(found, os.X_OK):
            return found
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


async def run(
    *cmd: str, cwd: Path | None = None, timeout: float = TIMEOUT, stderr: bool = False
) -> str:
    """stdout of ``cmd`` (and its stderr with *stderr*); UnavailableError when
    it can't run or fails."""
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
    return (out + err if stderr else out).decode(errors="replace")


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


async def python_row(cat: str) -> Row:
    """Python of the environment on disk; when the running process is older
    (`uv python upgrade` ran, the server didn't restart), say so."""
    import sys

    running = platform.python_version()
    try:
        on_disk = first_version(
            await run(sys.executable, "-c", "import platform; print(platform.python_version())")
        )
    except UnavailableError:
        on_disk = running
    result = await runtime_row(cat, "Python", "python", on_disk)
    if on_disk != running:
        result = row(
            cat,
            "Python",
            WARNING,
            f"{running} → {on_disk}",
            _("Python %(version)s is installed - restart the server to run on it.")
            % {"version": on_disk}
            + (" " + result["hint"] if result["status"] != OK else ""),
        )
    return result


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


_UV_UPDATE = re.compile(r"^Update (\S+) v(\S+) -> v(\S+)$", re.M)


def _uv() -> str:
    uv = tool("uv")
    if not uv:
        raise UnavailableError(_("uv is not installed"))
    return uv


async def framework_updates() -> list[str]:
    """What ``uv lock --upgrade`` would change in the framework's uv.lock -
    newer versions the declared ranges allow (a major blocked by another
    package's pin is not one)."""
    # uv reports the plan on stderr
    out = await run(
        _uv(), "lock", "--upgrade", "--dry-run", cwd=FRAMEWORK_DIR, timeout=60, stderr=True
    )
    return [f"{n} {a} → {b}" for n, a, b in _UV_UPDATE.findall(out)]


async def app_updates() -> list[str]:
    """Newer versions of the packages only apps depend on (not in uv.lock):
    what ``grunt app deps --upgrade`` would install."""
    from grunt.apps.deps import app_updates as plan

    try:
        return await asyncio.to_thread(plan, site_manager.bench_dir / "apps")
    except (OSError, subprocess.SubprocessError) as e:
        raise UnavailableError(str(e)) from e


async def npm_outdated() -> tuple[list[str], list[str]]:
    """``(updates, majors)``: newer versions package.json allows (what
    ``npm update`` takes), and newer ones only a changed range would."""
    npm = tool("npm")
    if not npm or not (FRAMEWORK_DIR / "node_modules").is_dir():
        raise UnavailableError(_("not installed"))
    out = await run(npm, "outdated", "--json", cwd=FRAMEWORK_DIR, timeout=60)
    updates, majors = [], []
    for name, info in json.loads(out or "{}").items():
        current, wanted, latest = info.get("current"), info.get("wanted"), info.get("latest")
        if not current:
            continue
        if wanted and wanted != current:
            updates.append(f"{name} {current} → {wanted}")
        if latest and latest != (wanted or current):
            majors.append(f"{name} {wanted or current} → {latest}")
    return updates, majors


def _state_key(*paths: Path) -> str:
    """Changes whenever a lock file or the installed packages change - a
    `grunt update` must not be answered from a cache made before it."""
    import sys
    import sysconfig

    site = Path(sysconfig.get_paths()["purelib"])
    stamps = [p.stat().st_mtime_ns if p.exists() else 0 for p in (*paths, site)]
    return f"{sys.executable}:{stamps}"


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
        _("Run `grunt update` - it offers to update the lock files; then commit them.")
        if settings.debug
        else _("Newer versions arrive with the next framework release.")
    )

    def updates_row(name: str, updates: list[str]) -> Row:
        if not updates:
            return row(cat, name, OK, _("up to date"))
        return row(
            cat,
            name,
            INFO,
            _("%(count)s newer versions") % {"count": len(updates)},
            hint + " " + short_list(updates),
        )

    py_key = _state_key(FRAMEWORK_DIR / "uv.lock")
    try:
        python = await cached(f"py:{py_key}", framework_updates)
        python += await cached(f"apps:{py_key}", app_updates)
    except UnavailableError as e:
        rows.append(_unavailable(cat, _("Python packages"), "", e))
    else:
        if not wrong or python:
            rows.append(updates_row(_("Python packages"), python))

    npm_key = _state_key(FRAMEWORK_DIR / "package-lock.json", FRAMEWORK_DIR / "node_modules")
    try:
        npm, majors = await cached(f"npm:{npm_key}", npm_outdated)
    except UnavailableError as e:
        rows.append(_unavailable(cat, _("npm packages"), "", e))
    else:
        rows.append(updates_row(_("npm packages"), npm))
        if majors:
            rows.append(
                row(
                    cat,
                    _("npm packages outside package.json"),
                    INFO,
                    str(len(majors)),
                    _("Outside the ranges in package.json - change them by hand and test:")
                    + " "
                    + short_list(majors),
                )
            )
    return rows


# Old runtimes - what `grunt update` cleans up at its end (grunt-cli's
# _cleanup_runtimes); the same rules, read-only.

_MISE_PRUNABLE = re.compile(r"^mise (\S+?)@(\S+) is prunable", re.M)
_SKIP_WALK = {"node_modules", ".cache", ".git", ".npm", "site-packages", "dist"}


def _in_use() -> dict[str, list[str]]:
    """``{real path: [who]}`` - the Python of every venv in the home directory
    and the executable of every running process."""
    used: dict[str, list[str]] = {}
    home = Path.home()
    for root, dirs, files in os.walk(home):
        depth = len(Path(root).relative_to(home).parts)
        dirs[:] = [d for d in dirs if d not in _SKIP_WALK and depth < 6]
        if "pyvenv.cfg" in files:
            for value in _cfg_values(Path(root) / "pyvenv.cfg", "home"):
                used.setdefault(os.path.realpath(value), []).append(_venv_user(Path(root)))
    for exe in Path("/proc").glob("[0-9]*/exe"):
        try:
            path = os.path.realpath(exe)
        except OSError:
            continue
        used.setdefault(path, []).append(_process_user(exe.parent))
    return used


def _home_path(path: Path) -> str:
    home = Path.home()
    return "~/" + str(path.relative_to(home)) if path.is_relative_to(home) else str(path)


def _venv_user(venv: Path) -> str:
    """ "venv ~/x → `the command that moves it to the current Python`"."""
    import sys

    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    tools = Path(os.environ.get("UV_TOOL_DIR") or Path.home() / ".local/share/uv/tools")
    if venv.parent == tools:
        who = _("uv tool %(name)s") % {"name": venv.name}
        fix = f"uv tool install --reinstall --python {py} {venv.name}"
    elif (venv.parent / "pyproject.toml").is_file():
        who = _("venv %(path)s") % {"path": _home_path(venv)}
        fix = f"cd {_home_path(venv.parent)} && uv sync --python {py}"
    else:
        who = _("venv %(path)s") % {"path": _home_path(venv)}
        # A standalone venv: its packages are recorded nowhere but in it -
        # save the list, recreate, install it back.
        shown = _home_path(venv)
        reqs = f"/tmp/{venv.name.lstrip('.') or 'venv'}-requirements.txt"
        fix = (
            f"uv pip freeze --python {shown} > {reqs}"
            f" && uv venv --clear --python {py} {shown}"
            f" && uv pip install --python {shown} -r {reqs}"
        )
    return f"{who} → `{fix}`"


def _process_user(proc: Path) -> str:
    """ "process 123 (grunt serve, 6 d) → `kill 123`"."""
    try:
        raw = (proc / "cmdline").read_bytes().split(b"\0")
        stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        raw, stat = [], []
    argv = [a.decode(errors="replace") for a in raw if a]
    # python /path/bin/grunt serve → grunt serve
    if len(argv) > 1 and Path(argv[0]).name.startswith("python"):
        argv = argv[1:]
    command = " ".join([Path(argv[0]).name, *argv[1:3]]) if argv else "?"
    pid = proc.name
    params = {"pid": pid, "command": command, "age": _age(stat)}
    if stat and stat[0] == "T":
        # Stopped (Ctrl+Z): ignores SIGTERM until woken up.
        who = _("process %(pid)s (%(command)s, %(age)s, stopped with Ctrl+Z)") % params
        return f"{who} → `kill {pid} && kill -CONT {pid}`"
    return f"{_('process %(pid)s (%(command)s, %(age)s)') % params} → `kill {pid}`"


def _age(stat: list[str]) -> str:
    try:
        start = int(stat[19])
        # btime, not /proc/uptime: in a container (LXC) uptime counts from the
        # container's start, the process start time - from the host's boot.
        btime = next(
            int(line.split()[1])
            for line in Path("/proc/stat").read_text().splitlines()
            if line.startswith("btime ")
        )
    except OSError, ValueError, IndexError, StopIteration:
        return "?"
    seconds = time.time() - (btime + start / os.sysconf("SC_CLK_TCK"))
    if seconds >= 86400:
        return _("%(n)s d") % {"n": int(seconds // 86400)}
    if seconds >= 3600:
        return _("%(n)s h") % {"n": int(seconds // 3600)}
    return _("%(n)s min") % {"n": max(int(seconds // 60), 1)}


def _cfg_values(path: Path, key: str) -> list[str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    return [v.strip() for k, _sep, v in (ln.partition("=") for ln in lines) if k.strip() == key]


def _cli_dir() -> Path | None:
    """grunt-cli's checkout, from its uv tool receipt (editable install)."""
    tools = Path(os.environ.get("UV_TOOL_DIR") or Path.home() / ".local/share/uv/tools")
    try:
        receipt = tomllib.loads((tools / "grunt-cli" / "uv-receipt.toml").read_text())
        editable = receipt["tool"]["requirements"][0].get("editable")
    except OSError, KeyError, IndexError, tomllib.TOMLDecodeError:
        editable = None
    if editable and Path(editable).is_dir():
        return Path(editable)
    default = Path.home() / ".grunt-cli"
    return default if default.is_dir() else None


def old_runtimes() -> tuple[list[str], list[str]]:
    """``(free, held)``: old uv Pythons / mise tool versions `grunt update`
    would remove, and the ones still in use (with who uses them)."""
    import subprocess
    import sys

    used = _in_use()
    free: list[str] = []
    held: list[str] = []

    def sort(label: str, directory: Path) -> None:
        prefix = f"{directory}/"
        users = [w for path, who in used.items() if path.startswith(prefix) for w in who]
        if users:
            held.append(f"{label} — {', '.join(users)}")
        else:
            free.append(label)

    managed = Path.home() / ".local/share/uv/python"
    current = {Path(os.path.realpath(sys.executable)).parent.parent}
    tools_dir = Path(os.environ.get("UV_TOOL_DIR") or Path.home() / ".local/share/uv/tools")
    for value in _cfg_values(tools_dir / "grunt-cli" / "pyvenv.cfg", "home"):
        current.add(Path(os.path.realpath(value)).parent)
    if uv := tool("uv"):
        out = subprocess.run(
            [uv, "python", "list", "--only-installed", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        seen: set[str] = set()
        for py in json.loads(out or "[]"):
            path = os.path.realpath(py.get("path") or "")
            if not path.startswith(f"{managed}/") or py["key"] in seen:
                continue
            seen.add(py["key"])
            install = managed / path.removeprefix(f"{managed}/").split("/", 1)[0]
            if install not in current:
                sort(f"Python {py.get('version') or py['key']} (uv)", install)

    if mise := tool("mise"):
        names: set[str] = set()
        cli = _cli_dir()
        for cfg in (FRAMEWORK_DIR / "mise.toml", cli and cli / "mise.toml"):
            if cfg and cfg.is_file():
                names.update(tomllib.loads(cfg.read_text()).get("tools", {}))
        if names:
            plan = subprocess.run(
                [mise, "prune", "--dry-run", *sorted(names)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            installs = Path.home() / ".local/share/mise/installs"
            for name, version in _MISE_PRUNABLE.findall(plan.stdout + plan.stderr):
                sort(f"{name} {version} (mise)", installs / name / version)
    return free, held


async def old_runtimes_row(cat: str) -> Row:
    check = _("Old runtime versions")
    try:
        free, held = await asyncio.to_thread(old_runtimes)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return _unavailable(cat, check, "", e)
    if not free and not held:
        return row(cat, check, OK, _("none"))
    hints = []
    if free:
        hints.append(_("`grunt update` removes: %(list)s.") % {"list": ", ".join(free)})
    if held:
        hints.append(
            _("Still in use, removed once free (how to free it after →): %(list)s.")
            % {"list": "; ".join(held)}
        )
    return row(cat, check, INFO, str(len(free) + len(held)), " ".join(hints))


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
        rows = [await python_row(cat)]
        try:
            node = await node_version()
        except UnavailableError:
            return rows
        return [*rows, await runtime_row(cat, "Node.js", "nodejs", node)]

    code, rts, tools, packages, old = await asyncio.gather(
        code_rows(cat), runtimes(), tool_rows(cat), package_rows(cat), old_runtimes_row(cat)
    )
    return [*code, *rts, *tools, old, *packages]
