"""Tests for app startup and workspace seeding functionality."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.startup import _load_app_meta, _auto_seed_workspace
from grunt.core.db.system_tables import GruntWorkspace, GruntWorkspaceLink


class TestLoadAppMeta:
    """Test _load_app_meta function."""

    def test_load_app_meta_from_app_json(self, tmp_path):
        """Test loading metadata from app.json only."""
        app_dir = tmp_path / "test_app"
        app_dir.mkdir()

        app_json = app_dir / "app.json"
        app_json.write_text(json.dumps({
            "name": "test_app",
            "title": "Test App",
            "version": "1.0.0",
            "description": "A test application",
            "author": "Test Author",
            "modules": ["core"],
            "icon": "🧪",
            "color": "#FF5733",
        }))

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
        app_json.write_text(json.dumps({
            "title": "Title from JSON",
            "modules": ["new_module"],
        }))

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


class TestAutoSeedWorkspace:
    """Test _auto_seed_workspace function."""

    async def test_auto_seed_workspace_empty_doctypes(self, db_session: AsyncSession):
        """Test workspace creation with empty doctypes list."""
        app_meta = {
            "name": "hr_oms",
            "title": "HR OMS System",
            "icon": "🙂",
            "color": "#3498db",
            "description": "HR management system",
            "modules": [],
        }

        await _auto_seed_workspace("hr_oms", app_meta, [], db_session)
        await db_session.commit()

        result = await db_session.execute(
            select(GruntWorkspace).where(GruntWorkspace.name == "hr_oms")
        )
        workspace = result.scalar_one_or_none()

        assert workspace is not None
        assert workspace.name == "hr_oms"
        assert workspace.label == "HR OMS System"
        assert workspace.icon == "🙂"
        assert workspace.color == "#3498db"
        assert workspace.description == "HR management system"
        assert workspace.app == "hr_oms"

    async def test_auto_seed_workspace_update_existing(self, db_session: AsyncSession):
        """Test workspace update when it already exists."""
        import uuid

        # Create initial workspace
        initial_id = str(uuid.uuid4())
        db_session.add(GruntWorkspace(
            id=initial_id,
            name="hr_oms",
            label="Old Label",
            app="hr_oms",
            icon="📄",
            color="#000000",
            description="Old description",
            sequence=10,
            is_hidden=False,
            roles="",
        ))
        await db_session.commit()

        # Call _auto_seed_workspace with new metadata
        app_meta = {
            "name": "hr_oms",
            "title": "HR OMS System Updated",
            "icon": "🙂",
            "color": "#3498db",
            "description": "Updated description",
            "modules": [],
        }

        await _auto_seed_workspace("hr_oms", app_meta, [], db_session)
        await db_session.commit()

        result = await db_session.execute(
            select(GruntWorkspace).where(GruntWorkspace.name == "hr_oms")
        )
        workspace = result.scalar_one_or_none()

        assert workspace is not None
        assert workspace.id == initial_id  # Same ID
        assert workspace.label == "HR OMS System Updated"  # Updated
        assert workspace.icon == "🙂"  # Updated
        assert workspace.color == "#3498db"  # Updated
