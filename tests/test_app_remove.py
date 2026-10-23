"""`grunt app remove`: the app leaves the bench - package uninstalled, directory archived."""

import json
import tarfile

import pytest
from click.testing import CliRunner

from grunt.apps import deps
from grunt.cli import app as app_cli
from grunt.site.manager import site_manager
from grunt.testkit import write_app_manifest


@pytest.fixture
def bench(tmp_path, monkeypatch, uninstalls):
    (tmp_path / "apps").mkdir()
    (tmp_path / "sites" / "site1").mkdir(parents=True)
    _site(tmp_path, ["grunt", "hrm"])
    for name, depends_on in [("grunt", []), ("hrm", []), ("cms", []), ("portal", ["cms"])]:
        project = {"name": "grunt-hrm" if name == "hrm" else name}
        write_app_manifest(tmp_path / "apps" / name, project, depends_on=depends_on)
    (tmp_path / "apps" / "hrm" / "__pycache__").mkdir()
    (tmp_path / "apps" / "hrm" / "__pycache__" / "x.pyc").write_bytes(b"")
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", tmp_path / "sites")
    return tmp_path


@pytest.fixture
def uninstalls(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(deps, "uv_binary", lambda: "/bin/uv")
    monkeypatch.setattr(deps.subprocess, "run", lambda cmd, check: calls.append(cmd))
    return calls


def _site(bench, installed):
    site_file = bench / "sites" / "site1" / "grunt.site"
    site_file.write_text(json.dumps({"installed_apps": installed}))


def _remove(*args):
    return CliRunner().invoke(app_cli.app_group, ["remove", *args])


def test_installed_on_a_site_is_refused(bench):
    result = _remove("hrm", "-y")
    assert result.exit_code != 0
    assert "installed on site site1" in result.output
    assert (bench / "apps" / "hrm").is_dir()


def test_dependency_of_another_app_is_refused(bench):
    result = _remove("cms", "-y")
    assert result.exit_code != 0
    assert "app 'portal' depends on it" in result.output
    assert (bench / "apps" / "cms").is_dir()


def test_core_app_is_refused(bench):
    assert _remove("grunt", "-y").exit_code != 0


def test_archives_and_uninstalls_package(bench, uninstalls):
    _site(bench, ["grunt"])
    result = _remove("hrm", "-y")
    assert result.exit_code == 0, result.output
    assert not (bench / "apps" / "hrm").exists()
    [archived] = (bench / "archive" / "apps").iterdir()
    assert archived.name.startswith("hrm-")
    assert archived.name.endswith(".tar.zst")
    with tarfile.open(archived, "r:zst") as tar:
        names = tar.getnames()
    assert "hrm/pyproject.toml" in names
    assert not any("__pycache__" in n for n in names)
    assert uninstalls == [
        ["/bin/uv", "pip", "uninstall", "--python", deps.sys.executable, "grunt-hrm"]
    ]


def test_no_archive_deletes(bench, uninstalls):
    result = _remove("portal", "-y", "--no-archive")
    assert result.exit_code == 0, result.output
    assert not (bench / "apps" / "portal").exists()
    assert not (bench / "archive").exists()
    assert uninstalls == [
        ["/bin/uv", "pip", "uninstall", "--python", deps.sys.executable, "portal"]
    ]


def test_force_overrides_checks(bench):
    result = _remove("cms", "-y", "--force")
    assert result.exit_code == 0, result.output
    assert not (bench / "apps" / "cms").exists()
