"""Bench apps' Python dependencies are installed as editable packages."""

from __future__ import annotations

from grunt.apps import deps


def _bench(tmp_path):
    layout = [("grunt", True), ("inventory", True), ("letter", False), ("hrm", True)]
    for name, has_pyproject in layout:
        (tmp_path / name).mkdir()
        if has_pyproject:
            (tmp_path / name / "pyproject.toml").write_text("[project]\n")
    return tmp_path


def test_only_app_packages_are_selected(tmp_path):
    apps = _bench(tmp_path)
    assert [d.name for d in deps.app_packages(apps)] == ["hrm", "inventory"]
    assert [d.name for d in deps.app_packages(apps, ["inventory"])] == ["inventory"]


def test_install_runs_one_editable_install(tmp_path, monkeypatch):
    apps = _bench(tmp_path)
    calls = []
    monkeypatch.setattr(deps, "uv_binary", lambda: "/bin/uv")
    monkeypatch.setattr(deps.subprocess, "run", lambda cmd, check: calls.append(cmd))
    assert deps.install_app_packages(apps) == ["hrm", "inventory"]
    [cmd] = calls
    assert cmd[cmd.index("-e") :] == ["-e", str(apps / "hrm"), "-e", str(apps / "inventory")]
    assert "--upgrade-package" not in cmd


def test_upgrade_moves_only_app_only_packages(tmp_path, monkeypatch):
    apps = _bench(tmp_path)
    (apps / "grunt").mkdir(exist_ok=True)
    (apps / "grunt" / "uv.lock").write_text('[[package]]\nname = "httpx2"\nversion = "1"\n')
    (apps / "hrm" / "pyproject.toml").write_text(
        '[project]\nname = "hrm"\ndependencies = ["httpx2", "ijson>=3.3"]\n'
    )
    calls = []
    monkeypatch.setattr(deps, "uv_binary", lambda: "/bin/uv")
    monkeypatch.setattr(deps.subprocess, "run", lambda cmd, check: calls.append(cmd))
    deps.install_app_packages(apps, upgrade=True)
    [cmd] = calls
    assert cmd[cmd.index("--upgrade-package") : cmd.index("-e")] == ["--upgrade-package", "ijson"]


def test_nothing_to_install(tmp_path, monkeypatch):
    (tmp_path / "letter").mkdir()

    def fail(*_a, **_k):
        raise AssertionError("nothing should be installed")

    monkeypatch.setattr(deps.subprocess, "run", fail)
    assert deps.install_app_packages(tmp_path) == []
