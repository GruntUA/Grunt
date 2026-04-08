"""Tests for CLI create-app command."""

from __future__ import annotations

import importlib
import json


class TestCreateApp:
    """Test create-app CLI command."""

    def test_create_app_scaffolding(self, tmp_path):
        """Test that create-app generates module-based structure with correct metadata."""
        name = "test_app"
        label = name.replace("_", " ").title()
        default_module = "core"

        # Create the app directory structure
        app_dir = tmp_path / name
        (app_dir / default_module / "doctypes").mkdir(parents=True)
        (app_dir / default_module / "fixtures").mkdir(parents=True)
        (app_dir / default_module / "tasks").mkdir(parents=True)
        (app_dir / default_module / "hooks").mkdir(parents=True)

        # Create __init__.py files
        (app_dir / "__init__.py").write_text(f'"""Grunt app: {label}"""\n\n__version__ = "0.1.0"\n')
        (app_dir / default_module / "__init__.py").write_text(
            f'"""Module {default_module} for {label}."""\n'
        )
        (app_dir / default_module / "doctypes" / "__init__.py").write_text("")
        (app_dir / default_module / "fixtures" / "__init__.py").write_text("")
        (app_dir / default_module / "tasks" / "__init__.py").write_text("")
        (app_dir / default_module / "hooks" / "__init__.py").write_text("")

        # app.json with full metadata
        app_json_content = {
            "name": name,
            "title": label,
            "version": "0.1.0",
            "description": f"{label} Grunt app",
            "author": "",
            "modules": [default_module],
            "icon": "📦",
            "color": "#2D6A4F",
        }
        (app_dir / "app.json").write_text(
            json.dumps(app_json_content, ensure_ascii=False, indent=2) + "\n"
        )

        # grunt_app.py
        (app_dir / "grunt_app.py").write_text(
            f'"""Metadata for {label}."""\n\n'
            f'APP_NAME = "{name}"\n'
            f'APP_TITLE = "{label}"\n'
            f'APP_VERSION = "0.1.0"\n'
            f'APP_DESCRIPTION = "{label} Grunt app"\n'
            f'APP_AUTHOR = ""\n'
            f'APP_ICON = "📦"\n'
            f'APP_COLOR = "#2D6A4F"\n'
            f'MODULES = ["{default_module}"]\n'
            f"DEPENDS_ON = []\n"
        )

        # fixtures/00_workspace.json (inside module)
        (app_dir / default_module / "fixtures" / "00_workspace.json").write_text(
            json.dumps(
                [
                    {
                        "name": name,
                        "label": label,
                        "icon": "📦",
                        "color": "#2D6A4F",
                        "description": "",
                        "items": [],
                    }
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )

        # Verify all files exist
        assert (app_dir / "app.json").exists()
        assert (app_dir / "grunt_app.py").exists()
        assert (app_dir / default_module / "fixtures" / "00_workspace.json").exists()
        assert (app_dir / "__init__.py").exists()
        assert (app_dir / default_module / "tasks").is_dir()
        assert (app_dir / default_module / "hooks").is_dir()
        assert (app_dir / default_module / "doctypes").is_dir()

        # Verify app.json content
        app_json = json.loads((app_dir / "app.json").read_text())
        assert app_json["name"] == "test_app"
        assert app_json["title"] == "Test App"
        assert app_json["version"] == "0.1.0"
        assert app_json["modules"] == ["core"]
        spec = importlib.util.spec_from_file_location(
            "test_app_meta",
            app_dir / "grunt_app.py",
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            assert module.APP_NAME == "test_app"
            assert module.APP_TITLE == "Test App"
            assert [default_module] == module.MODULES
            assert module.APP_ICON == "📦"
            assert module.APP_COLOR == "#2D6A4F"

        # Verify fixtures content
        fixtures = json.loads(
            (app_dir / default_module / "fixtures" / "00_workspace.json").read_text()
        )
        assert isinstance(fixtures, list)
        assert len(fixtures) == 1
        assert fixtures[0]["name"] == "test_app"
        assert fixtures[0]["label"] == "Test App"
        assert fixtures[0]["icon"] == "📦"
        assert fixtures[0]["items"] == []
