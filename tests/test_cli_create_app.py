"""``grunt app create`` scaffolds an app the bench can install and lint."""

import json
import tomllib

from grunt.utils.boilerplate import _create_app_boilerplate

HOOKS = {
    "app_name": "test_app",
    "title": "Test App",
    "description": "Test App — Grunt app",
    "author": "Tester",
    "email": "t@example.com",
    "icon": "package",
    "module": "core",
}


def test_create_app_scaffolding(tmp_path):
    _create_app_boilerplate(tmp_path, HOOKS, no_git=True)
    app_dir = tmp_path / "test_app"

    app_json = json.loads((app_dir / "app.json").read_text())
    assert app_json["name"] == "test_app"
    assert app_json["modules"] == ["core"]

    # Fixture files use the {doctype, records} shape the fixture loader reads.
    workspace = json.loads((app_dir / "core" / "fixtures" / "00_workspace.json").read_text())
    assert workspace["doctype"] == "AppMenu"
    assert [r["name"] for r in workspace["records"]] == ["test_app"]
    assert workspace["records"][0]["items"] == []

    project = tomllib.loads((app_dir / "pyproject.toml").read_text())
    assert project["project"]["name"] == "test_app"
    assert project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["core"]

    pyright = json.loads((app_dir / "pyrightconfig.json").read_text())
    assert pyright["include"] == ["core"]

    for rel in ("install.py", "core/hooks.py", "core/routes.py", "core/doctypes"):
        assert (app_dir / rel).exists(), rel
