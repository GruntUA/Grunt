"""Apps' ``depends_on``: missing dependencies join the site, absent ones get cloned."""

import json

import pytest

from grunt.apps import required
from grunt.testkit import write_app_manifest

CMS_URL = "https://example.com/cms.git"


def _app(apps, name, depends_on=()):
    write_app_manifest(apps / name, depends_on=list(depends_on))


def test_both_entry_forms(tmp_path):
    _app(tmp_path, "portal", ["grunt", "hrm", {"name": "cms", "url": CMS_URL}])
    assert required.dependencies(tmp_path / "portal") == [
        required.Dependency("hrm"),
        required.Dependency("cms", CMS_URL),
    ]


def test_dependencies_go_before_their_user(tmp_path):
    _app(tmp_path, "cms")
    _app(tmp_path, "hrm")
    _app(tmp_path, "portal", ["cms"])
    _app(tmp_path, "letter", ["hrm"])
    installed = ["grunt", "hrm", "portal", "letter"]
    assert required.with_dependencies(tmp_path, installed) == [
        "grunt",
        "hrm",
        "cms",
        "portal",
        "letter",
    ]


def test_missing_dependency_names_the_clone(tmp_path):
    _app(tmp_path, "portal", [{"name": "cms", "url": CMS_URL}])
    with pytest.raises(required.MissingAppError, match=f"git clone {CMS_URL} apps/cms"):
        required.with_dependencies(tmp_path, ["portal"])


def test_cycle_is_reported(tmp_path):
    _app(tmp_path, "a", ["b"])
    _app(tmp_path, "b", ["a"])
    with pytest.raises(required.DependencyCycleError, match="a -> b -> a"):
        required.with_dependencies(tmp_path, ["a"])


def test_site_file_gets_the_dependency(tmp_path):
    apps = tmp_path / "apps"
    _app(apps, "cms")
    _app(apps, "portal", ["cms"])
    site_file = tmp_path / "grunt.site"
    site_file.write_text(json.dumps({"installed_apps": ["grunt", "portal"]}))

    assert required.ensure_site_dependencies(site_file, apps) == ["cms"]
    config = json.loads(site_file.read_text())
    assert config["installed_apps"] == ["grunt", "cms", "portal"]
    assert required.ensure_site_dependencies(site_file, apps) == []


def test_clone_missing_follows_the_cloned_app(tmp_path, monkeypatch):
    _app(tmp_path, "portal", [{"name": "cms", "url": CMS_URL}, "hrm"])
    calls = []

    def fake_clone(cmd, check):
        calls.append(cmd)
        target = tmp_path / cmd[-1].rsplit("/", 1)[-1]
        deps = [{"name": "media", "url": "https://example.com/media.git"}]
        _app(tmp_path, target.name, deps if target.name == "cms" else ())

    monkeypatch.setattr(required.subprocess, "run", fake_clone)
    assert required.clone_missing(tmp_path) == ["cms", "media"]
    assert calls[0] == ["git", "clone", CMS_URL, str(tmp_path / "cms")]
    assert required.clone_missing(tmp_path) == []
