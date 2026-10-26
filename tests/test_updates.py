"""Available updates in the health report (grunt.monitoring.updates)."""

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from grunt.monitoring import updates

CAT = "Updates"


@pytest.fixture(autouse=True)
def _fresh_cache():
    updates.clear_cache()
    yield
    updates.clear_cache()


def _cycles(monkeypatch, cycles):
    async def fake(product):
        return cycles

    monkeypatch.setattr(updates, "_cycles", fake)


def _future(days: int = 365) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# Runtimes


@pytest.mark.asyncio
async def test_runtime_newer_patch_is_a_warning(monkeypatch):
    _cycles(monkeypatch, [{"cycle": "3.14", "latest": "3.14.8", "eol": _future()}])
    r = await updates.runtime_row(CAT, "Python", "python", "3.14.4")
    assert r["status"] == "Warning"
    assert r["value"] == "3.14.4 → 3.14.8"
    assert "grunt update" in r["hint"]


@pytest.mark.asyncio
async def test_mise_skips_releases_younger_than_a_day(monkeypatch):
    # mise self-update doesn't take a release younger than 24h - neither does the row
    now = datetime.now(UTC)
    releases = [
        {"tag_name": "v2026.10.12", "published_at": (now - timedelta(hours=3)).isoformat()},
        {"tag_name": "v2026.10.11", "published_at": (now - timedelta(days=2)).isoformat()},
    ]

    async def fake_fetch(url):
        assert "jdx/mise" in url
        return json.dumps(releases)

    async def fake_run(*cmd, **kwargs):
        return "2026.10.11 linux-x64"

    from grunt.storage.cloud import rclone

    monkeypatch.setattr(rclone, "is_installed", lambda: False)
    monkeypatch.setattr(updates, "tool", lambda name: "/bin/mise" if name == "mise" else None)
    monkeypatch.setattr(updates, "run", fake_run)
    monkeypatch.setattr(updates, "fetch", fake_fetch)
    rows = await updates.tool_rows(CAT)
    assert [(r["check"], r["status"], r["value"]) for r in rows] == [("mise", "OK", "2026.10.11")]


@pytest.mark.asyncio
async def test_uv_skips_releases_younger_than_a_day(monkeypatch):
    # mise.toml has uv = "latest": `mise upgrade` waits a day too
    now = datetime.now(UTC)

    def uploaded(**age):
        return [{"upload_time_iso_8601": (now - timedelta(**age)).isoformat()}]

    pypi = {
        "releases": {
            "0.13.5": uploaded(hours=23),
            "0.14.0rc1": uploaded(days=3),
            "0.13.4": uploaded(days=2),
            "0.13.3": uploaded(days=9),
        }
    }

    async def fake_fetch(url):
        assert "pypi.org/pypi/uv" in url
        return json.dumps(pypi)

    async def fake_run(*cmd, **kwargs):
        return "uv 0.13.4 (x86_64-unknown-linux-gnu)"

    from grunt.storage.cloud import rclone

    monkeypatch.setattr(rclone, "is_installed", lambda: False)
    monkeypatch.setattr(updates, "tool", lambda name: "/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(updates, "run", fake_run)
    monkeypatch.setattr(updates, "fetch", fake_fetch)
    rows = await updates.tool_rows(CAT)
    assert [(r["check"], r["status"], r["value"]) for r in rows] == [("uv", "OK", "0.13.4")]


@pytest.mark.asyncio
async def test_runtime_up_to_date_mentions_newer_line(monkeypatch):
    _cycles(
        monkeypatch,
        [
            {"cycle": "3.15", "latest": "3.15.0", "eol": _future(2000)},
            {"cycle": "3.14", "latest": "3.14.8", "eol": _future()},
        ],
    )
    r = await updates.runtime_row(CAT, "Python", "python", "3.14.8")
    assert r["status"] == "Info"
    assert "3.15" in r["hint"]


@pytest.mark.asyncio
async def test_runtime_past_end_of_life_is_an_error(monkeypatch):
    _cycles(monkeypatch, [{"cycle": "24", "latest": "24.9.0", "eol": "2020-01-01"}])
    r = await updates.runtime_row(CAT, "Node.js", "nodejs", "24.9.0")
    assert r["status"] == "Error"


@pytest.mark.asyncio
async def test_unreachable_source_is_info_and_cached(monkeypatch):
    calls = []

    async def down(product):
        calls.append(product)
        raise updates.UnavailableError("offline")

    monkeypatch.setattr(updates, "_cycles", down)
    for _ in range(2):
        r = await updates.runtime_row(CAT, "Python", "python", "3.14.4")
        assert r["status"] == "Info"
        assert "offline" in r["hint"]
    assert calls == ["python"]


@pytest.mark.asyncio
async def test_tool_row(monkeypatch):
    async def have():
        return "1.70.0"

    async def latest():
        return "1.75.2"

    r = await updates.tool_row(CAT, "rclone", have, latest)
    assert r is not None and r["value"] == "1.70.0 → 1.75.2"

    async def missing():
        raise updates.UnavailableError("not installed")

    assert await updates.tool_row(CAT, "rclone", missing, latest) is None


# Git


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _commit(repo, name):
    (repo / name).write_text(name)
    _git(repo, "add", name)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", name)


@pytest.fixture
def repos(tmp_path):
    """An "origin" and a clone of it."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "master")
    _commit(origin, "a")
    _git(tmp_path, "clone", "-q", str(origin), "clone")
    return origin, tmp_path / "clone"


@pytest.mark.asyncio
async def test_branch_behind_origin(repos):
    origin, clone = repos
    assert await updates.repo_update(clone) is None
    _commit(origin, "b")
    assert await updates.repo_update(clone) == "origin/master"


@pytest.mark.asyncio
async def test_branch_ahead_of_origin(repos):
    _origin, clone = repos
    _commit(clone, "local")
    assert await updates.repo_update(clone) is None


@pytest.mark.asyncio
async def test_release_tag_behind(repos):
    origin, clone = repos
    _git(origin, "tag", "v0.1.0")
    _git(clone, "fetch", "-q", "--tags")
    _git(clone, "checkout", "-q", "--detach", "v0.1.0")
    assert await updates.repo_update(clone) is None

    _commit(origin, "b")
    _git(origin, "tag", "v0.2.0")
    _git(origin, "tag", "v0.3.0-rc1")  # not a release
    assert await updates.repo_update(clone) == "v0.2.0"


# Packages


def test_lock_mismatches(tmp_path, monkeypatch):
    installed = importlib.metadata.version("packaging")
    (tmp_path / "uv.lock").write_text(
        f"""
[[package]]
name = "packaging"
version = "{installed}"
source = {{ registry = "https://pypi.org/simple" }}

[[package]]
name = "pydantic"
version = "0.0.1"
source = {{ registry = "https://pypi.org/simple" }}

[[package]]
name = "grunt"
version = "0.0.1"
source = {{ editable = "." }}

[[package]]
name = "not-installed-anywhere"
version = "1.0"
source = {{ registry = "https://pypi.org/simple" }}
"""
    )
    monkeypatch.setattr(updates, "FRAMEWORK_DIR", tmp_path)
    wrong = updates.lock_mismatches()
    assert len(wrong) == 1 and wrong[0].startswith("pydantic ")


@pytest.mark.asyncio
async def test_framework_updates_reads_the_uv_plan(monkeypatch):
    async def fake_run(*cmd, **kwargs):
        assert cmd[1:4] == ("lock", "--upgrade", "--dry-run") and kwargs.get("stderr")
        return (
            "Resolved 130 packages in 768ms\n"
            "Update aiohttp v3.14.4 -> v3.14.5\n"
            "Update pydantic-core v2.50.0 -> v2.50.1\n"
        )

    monkeypatch.setattr(updates, "tool", lambda name: f"/bin/{name}")
    monkeypatch.setattr(updates, "run", fake_run)
    assert await updates.framework_updates() == [
        "aiohttp 3.14.4 → 3.14.5",
        "pydantic-core 2.50.0 → 2.50.1",
    ]


@pytest.mark.asyncio
async def test_npm_outdated_splits_reachable_from_majors(monkeypatch, tmp_path):
    (tmp_path / "node_modules").mkdir()

    async def fake_run(*cmd, **kwargs):
        return """{
          "vue": {"current": "3.5.1", "wanted": "3.5.4", "latest": "3.5.4"},
          "vitest": {"current": "4.1.11", "wanted": "4.1.11", "latest": "5.0.4"},
          "pinia": {"current": "3.0.0", "wanted": "3.0.2", "latest": "4.0.0"},
          "missing": {"wanted": "1.0.0", "latest": "1.0.0"}
        }"""

    monkeypatch.setattr(updates, "FRAMEWORK_DIR", tmp_path)
    monkeypatch.setattr(updates, "tool", lambda name: f"/bin/{name}")
    monkeypatch.setattr(updates, "run", fake_run)
    reachable, majors = await updates.npm_outdated()
    assert reachable == ["vue 3.5.1 → 3.5.4", "pinia 3.0.0 → 3.0.2"]
    assert majors == ["vitest 4.1.11 → 5.0.4", "pinia 3.0.2 → 4.0.0"]


@pytest.mark.asyncio
async def test_python_row_asks_for_restart(monkeypatch):
    _cycles(monkeypatch, [{"cycle": "3.14", "latest": "3.99.0", "eol": _future()}])

    async def on_disk(*cmd, **kwargs):
        return "3.99.0\n"

    monkeypatch.setattr(updates, "run", on_disk)
    monkeypatch.setattr(platform, "python_version", lambda: "3.14.0")
    r = await updates.python_row(CAT)
    assert r["status"] == "Warning"
    assert r["value"] == "3.14.0 → 3.99.0"
    assert "3.99.0" in r["hint"]


@pytest.mark.parametrize(
    ("downloads", "status"),
    [(["3.14.4", "3.14.8"], "Warning"), (["3.14.4"], "Info")],
)
@pytest.mark.asyncio
async def test_python_patch_waits_for_uv(monkeypatch, downloads, status):
    # `uv python upgrade` takes only a patch the installed uv knows
    _cycles(monkeypatch, [{"cycle": "3.14", "latest": "3.14.8", "eol": _future()}])

    async def fake_run(*cmd, **kwargs):
        if "--only-downloads" in cmd:
            return json.dumps([{"version": v} for v in downloads])
        return "3.14.4\n"

    monkeypatch.setattr(updates, "run", fake_run)
    monkeypatch.setattr(updates, "tool", lambda name: "/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(platform, "python_version", lambda: "3.14.4")
    r = await updates.python_row(CAT)
    assert r["status"] == status
    assert "3.14.8" in (r["value"] if status == "Warning" else r["hint"])


def test_state_key_follows_the_lock_file(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text("a")
    before = updates._state_key(lock)
    import os

    os.utime(lock, ns=(1, 1))
    assert updates._state_key(lock) != before


def test_app_only_requirements(tmp_path):
    from grunt.apps.deps import app_only_requirements

    (tmp_path / "uv.lock").write_text('[[package]]\nname = "httpx2"\nversion = "1"\n')
    shop = tmp_path / "shop"
    shop.mkdir()
    (shop / "pyproject.toml").write_text(
        '[project]\nname = "shop"\ndependencies = ["HTTPX2>=1", "ijson>=3.3", "olefile",'
        ' "crm", "Pillow[webp] >=10 ; python_version>\'3\'"]\n'
    )
    crm = tmp_path / "crm"
    crm.mkdir()
    (crm / "pyproject.toml").write_text('[project]\nname = "crm"\n')
    assert app_only_requirements([shop, crm], tmp_path / "uv.lock") == [
        "ijson",
        "olefile",
        "pillow",
    ]


# Old runtimes


def test_old_runtimes(tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace

    home = tmp_path / "home"
    managed = home / ".local/share/uv/python"
    for v in ("3.14.4", "3.14.8", "3.15.0"):
        (managed / f"cpython-{v}-linux-x86_64-gnu" / "bin").mkdir(parents=True)
    # this process runs on 3.15.0 - the current one, never listed
    monkeypatch.setattr(
        sys, "executable", str(managed / "cpython-3.15.0-linux-x86_64-gnu/bin/python3")
    )
    # 3.14.8 is held by two venvs at once - both are shown, each with its fix
    old_home = f"home = {managed}/cpython-3.14.8-linux-x86_64-gnu/bin\n"
    venv = home / "other/.venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(old_home)
    (home / "other/pyproject.toml").write_text("")
    tool_venv = home / ".local/share/uv/tools/deptry"
    tool_venv.mkdir(parents=True)
    (tool_venv / "pyvenv.cfg").write_text(old_home)
    monkeypatch.delenv("UV_TOOL_DIR", raising=False)
    framework = tmp_path / "grunt"
    framework.mkdir()
    (framework / "mise.toml").write_text('[tools]\nnode = "26"\n')
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(updates, "FRAMEWORK_DIR", framework)
    monkeypatch.setattr(updates, "tool", lambda name: f"/bin/{name}")
    node = home / ".local/share/mise/installs/node/26.8.1/bin/node"
    real_in_use = updates._in_use
    monkeypatch.setattr(
        updates, "_in_use", lambda: {**real_in_use(), str(node): ["process 7 (node)"]}
    )
    listed = [
        {
            "key": f"cpython-{v}-linux-x86_64-gnu",
            "version": v,
            "path": f"{managed}/cpython-{v}-linux-x86_64-gnu/bin/python3",
        }
        for v in ("3.14.4", "3.14.8", "3.15.0")
    ]

    def fake_run(cmd, **kwargs):
        if cmd[1:3] == ["python", "list"]:
            return SimpleNamespace(stdout=json.dumps(listed), stderr="")
        assert cmd == ["/bin/mise", "prune", "--dry-run", "node"]
        return SimpleNamespace(
            stdout="", stderr="mise node@26.8.1 is prunable: node is required at 26.11.1\n"
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    free, held = updates.old_runtimes()
    assert free == ["Python 3.14.4 (uv)"]
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert held[0].startswith("Python 3.14.8 (uv) — ")
    assert f"venv ~/other/.venv → `cd ~/other && uv sync --python {py}`" in held[0]
    assert f"uv tool deptry → `uv tool install --reinstall --python {py} deptry`" in held[0]
    assert held[1] == "node 26.8.1 (mise) — process 7 (node)"


@pytest.mark.asyncio
async def test_old_runtimes_row(monkeypatch):
    monkeypatch.setattr(updates, "old_runtimes", lambda: ([], []))
    assert (await updates.old_runtimes_row(CAT))["status"] == "OK"

    monkeypatch.setattr(
        updates, "old_runtimes", lambda: (["uv 0.11.7 (mise)"], ["Python 3.14.4 (uv) — process 1"])
    )
    r = await updates.old_runtimes_row(CAT)
    assert r["status"] == "Info" and r["value"] == "2"
    assert "uv 0.11.7 (mise)" in r["hint"] and "process 1" in r["hint"]


def test_process_user(tmp_path, monkeypatch):
    import os
    import time

    proc = tmp_path / "proc" / "42"
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(b"/x/bin/python3\0/home/u/.local/bin/grunt\0serve\0")
    clk = os.sysconf("SC_CLK_TCK")
    btime = int(time.time()) - 10 * 86400
    started = 4 * 86400 * clk  # 4 days after boot -> 6 days ago
    fields = ["T", *["0"] * 18, str(started)]
    (proc / "stat").write_text(f"42 (python3) {' '.join(fields)}\n")
    real_read = Path.read_text

    def read_text(self, *a, **kw):
        if str(self) == "/proc/stat":
            return f"cpu 0\nbtime {btime}\n"
        return real_read(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", read_text)
    who = updates._process_user(proc)
    assert "42 (grunt serve, 6 " in who and "Ctrl+Z)" in who
    assert who.endswith("→ `kill 42 && kill -CONT 42`")

    (proc / "stat").write_text(f"42 (python3) S {' '.join(fields[1:])}\n")
    running = updates._process_user(proc)
    assert "Ctrl+Z" not in running and running.endswith(") → `kill 42`")


_UPGRADABLE = """Listing...
openssl/trixie-security 3.5.1-1+deb13u1 amd64 [upgradable from: 3.5.1-1]
curl/trixie 8.14.1-2 amd64 [upgradable from: 8.14.1-1]
"""


@pytest.fixture
def apt(monkeypatch, tmp_path):
    """A fake apt: ``apt.listing`` is what `apt list --upgradable` prints."""
    state = SimpleNamespace(listing="Listing...\n")

    async def fake_run(*cmd, **kwargs):
        assert cmd[:2] == ("apt", "list")
        return state.listing

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(updates, "run", fake_run)
    monkeypatch.setattr(updates, "os_name", lambda: "Debian GNU/Linux 13 (trixie)")
    monkeypatch.setattr(updates, "APT_LISTS", tmp_path)
    monkeypatch.setattr(updates, "REBOOT_REQUIRED", tmp_path / "reboot-required")
    state.dir = tmp_path
    return state


@pytest.mark.asyncio
async def test_os_up_to_date(apt):
    (apt.dir / "deb.debian.org_dists_trixie_InRelease").touch()
    r = await updates.os_row(CAT)
    assert r is not None
    assert r["status"] == "OK" and r["value"] == "Debian GNU/Linux 13 (trixie)"


@pytest.mark.asyncio
async def test_os_security_updates_are_an_error(apt):
    apt.listing = _UPGRADABLE
    r = await updates.os_row(CAT)
    assert r is not None
    assert r["status"] == "Error"
    assert "openssl, curl" in r["hint"] and "sudo apt upgrade" in r["hint"]  # security first


@pytest.mark.asyncio
async def test_os_stale_lists_and_reboot(apt):
    old = apt.dir / "deb.debian.org_dists_trixie_InRelease"
    old.touch()
    ten_days_ago = time.time() - 10 * 86400
    os.utime(old, (ten_days_ago, ten_days_ago))
    (apt.dir / "reboot-required").touch()
    r = await updates.os_row(CAT)
    assert r is not None
    assert r["status"] == "Warning"
    assert "10" in r["hint"] and "grunt update" in r["hint"]


@pytest.mark.asyncio
async def test_no_apt_no_os_row(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert await updates.os_row(CAT) is None
