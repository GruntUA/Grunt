"""Tests for app startup and workspace seeding functionality."""

from __future__ import annotations

import json

from grunt.core.startup import _load_app_meta


class TestLoadAppMeta:
    """Test _load_app_meta function."""

    def test_load_app_meta_from_app_json(self, tmp_path):
        """Test loading metadata from app.json only."""
        app_dir = tmp_path / "test_app"
        app_dir.mkdir()

        app_json = app_dir / "app.json"
        app_json.write_text(
            json.dumps(
                {
                    "name": "test_app",
                    "title": "Test App",
                    "version": "1.0.0",
                    "description": "A test application",
                    "author": "Test Author",
                    "modules": ["core"],
                    "icon": "🧪",
                    "color": "#FF5733",
                }
            )
        )

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "test_app"
        assert meta["title"] == "Test App"
        assert meta["version"] == "1.0.0"
        assert meta["description"] == "A test application"
        assert meta["author"] == "Test Author"
        assert meta["modules"] == ["core"]
        assert meta["icon"] == "🧪"
        assert meta["color"] == "#FF5733"

    def test_load_app_meta_from_grunt_app_py(self, tmp_path):
        """Test loading metadata from grunt_app.py only."""
        app_dir = tmp_path / "test_app"
        app_dir.mkdir()

        grunt_app = app_dir / "grunt_app.py"
        grunt_app.write_text(
            'APP_NAME = "test_app"\n'
            'APP_TITLE = "Test App from Py"\n'
            'APP_VERSION = "2.0.0"\n'
            'APP_ICON = "🎯"\n'
            'APP_COLOR = "#00FF00"\n'
            'MODULES = ["module1", "module2"]\n'
            'APP_DESCRIPTION = "Python metadata"\n'
        )

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "test_app"
        assert meta["title"] == "Test App from Py"
        assert meta["version"] == "2.0.0"
        assert meta["icon"] == "🎯"
        assert meta["color"] == "#00FF00"
        assert meta["modules"] == ["module1", "module2"]
        assert meta["description"] == "Python metadata"

    def test_load_app_meta_app_json_overrides_grunt_app(self, tmp_path):
        """Test that app.json values override grunt_app.py values."""
        app_dir = tmp_path / "test_app"
        app_dir.mkdir()

        # Create grunt_app.py with base metadata
        grunt_app = app_dir / "grunt_app.py"
        grunt_app.write_text(
            'APP_NAME = "test_app"\n'
            'APP_TITLE = "Title from Py"\n'
            'APP_ICON = "📄"\n'
            'MODULES = ["old_module"]\n'
        )

        # Create app.json that overrides some values
        app_json = app_dir / "app.json"
        app_json.write_text(
            json.dumps(
                {
                    "title": "Title from JSON",
                    "modules": ["new_module"],
                }
            )
        )

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "test_app"  # From grunt_app.py
        assert meta["title"] == "Title from JSON"  # Overridden by app.json
        assert meta["icon"] == "📄"  # From grunt_app.py
        assert meta["modules"] == ["new_module"]  # Overridden by app.json

    def test_load_app_meta_with_defaults(self, tmp_path):
        """Test that missing fields get default values."""
        app_dir = tmp_path / "test_app"
        app_dir.mkdir()

        # Empty app.json
        app_json = app_dir / "app.json"
        app_json.write_text("{}")

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "test_app"  # From directory name
        assert meta["title"] == "test_app"  # From directory name
        assert meta["version"] == "0.1.0"  # Default
        assert meta["modules"] == []  # Default
        assert meta["icon"] == "📦"  # Default
        assert meta["color"] == "#2D6A4F"  # Default
        assert meta["description"] == ""  # Default

    def test_load_app_meta_nonexistent_returns_defaults(self, tmp_path):
        """Test that nonexistent app directory still returns defaults."""
        app_dir = tmp_path / "nonexistent"

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "nonexistent"
        assert meta["icon"] == "📦"
        assert meta["modules"] == []
