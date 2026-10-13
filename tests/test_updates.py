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
