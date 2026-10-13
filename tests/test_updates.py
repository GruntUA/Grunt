"""Available updates in the health report (grunt.monitoring.updates)."""

from __future__ import annotations

import importlib.metadata
import subprocess
from datetime import date, timedelta

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
    monkeypatch.setattr(updates.platform, "python_version", lambda: "3.14.0")
    r = await updates.python_row(CAT)
    assert r["status"] == "Warning"
    assert r["value"] == "3.14.0 → 3.99.0"
    assert "3.99.0" in r["hint"]


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
    venv = home / "other/.venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = {managed}/cpython-3.14.8-linux-x86_64-gnu/bin\n")
    framework = tmp_path / "grunt"
    framework.mkdir()
    (framework / "mise.toml").write_text('[tools]\nnode = "26"\n')
    monkeypatch.setattr(updates.Path, "home", lambda: home)
    monkeypatch.setattr(updates, "FRAMEWORK_DIR", framework)
    monkeypatch.setattr(updates, "tool", lambda name: f"/bin/{name}")
    node = home / ".local/share/mise/installs/node/26.8.1/bin/node"
    real_in_use = updates._in_use
    monkeypatch.setattr(
        updates, "_in_use", lambda: {**real_in_use(), str(node): "process 7 (node)"}
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
    assert held[0].startswith("Python 3.14.8 (uv) — ") and "other/.venv" in held[0]
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
