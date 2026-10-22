"""Tests for app startup and workspace seeding functionality."""

import json

from grunt.startup.fixtures import _load_app_meta


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
                    "description": "A test application",
                    "author": "Test Author",
                    "modules": ["core"],
                }
            )
        )

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "test_app"
        assert meta["title"] == "Test App"
        assert meta["description"] == "A test application"
        assert meta["author"] == "Test Author"
        assert meta["modules"] == ["core"]

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
        assert meta["version"] == "0.0.0"  # No git
        assert meta["modules"] == []  # Default
        assert meta["description"] == ""  # Default

    def test_load_app_meta_nonexistent_returns_defaults(self, tmp_path):
        """Test that nonexistent app directory still returns defaults."""
        app_dir = tmp_path / "nonexistent"

        meta = _load_app_meta(app_dir)

        assert meta is not None
        assert meta["name"] == "nonexistent"
        assert meta["modules"] == []
