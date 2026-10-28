"""App manifest: [project] + [tool.grunt] of the app's pyproject.toml."""

from grunt.apps.manifest import is_app, read_manifest
from grunt.testkit import write_app_manifest


class TestReadManifest:
    def test_from_pyproject(self, tmp_path):
        """Test loading metadata from [project] and [tool.grunt]."""
        app_dir = tmp_path / "test_app"
        write_app_manifest(
            app_dir,
            {
                "name": "test_app",
                "description": "A test application",
                "authors": [{"name": "Test Author", "email": "a@example.com"}],
            },
            title="Test App",
            modules=["core"],
        )

        meta = read_manifest(app_dir)

        assert meta["name"] == "test_app"
        assert meta["title"] == "Test App"
        assert meta["description"] == "A test application"
        assert meta["author"] == "Test Author"
        assert meta["email"] == "a@example.com"
        assert meta["modules"] == ["core"]

    def test_with_defaults(self, tmp_path):
        """Test that missing fields get default values."""
        app_dir = tmp_path / "test_app"
        write_app_manifest(app_dir)

        meta = read_manifest(app_dir)

        assert meta["name"] == "test_app"  # From directory name
        assert meta["title"] == "test_app"  # From directory name
        assert meta["modules"] == ["test_app"]  # Default: the directory name
        assert meta["description"] == ""  # Default

    def test_nonexistent_returns_defaults(self, tmp_path):
        """Test that nonexistent app directory still returns defaults."""
        app_dir = tmp_path / "nonexistent"

        meta = read_manifest(app_dir)

        assert meta["name"] == "nonexistent"
        assert meta["modules"] == ["nonexistent"]

    def test_is_app_needs_tool_grunt(self, tmp_path):
        write_app_manifest(tmp_path / "app")
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "pyproject.toml").write_text('[project]\nname = "lib"\n')
        assert is_app(tmp_path / "app")
        assert not is_app(tmp_path / "lib")
        assert not is_app(tmp_path / "missing")


class TestExtends:
    def test_extends_implies_dependency_and_no_workspace(self, tmp_path):
        app_dir = tmp_path / "crystal"
        write_app_manifest(app_dir, extends=["inventory"], depends_on=["hrm"])

        meta = read_manifest(app_dir)

        assert meta["extends"] == ["inventory"]
        assert meta["depends_on"] == ["hrm", "inventory"]
        assert meta["workspace"] is False

    def test_extends_already_in_depends_on_not_duplicated(self, tmp_path):
        app_dir = tmp_path / "crystal"
        write_app_manifest(
            app_dir,
            extends=["inventory"],
            depends_on=[{"name": "inventory", "url": "https://example.com/inventory.git"}],
            workspace=True,
        )

        meta = read_manifest(app_dir)

        assert len(meta["depends_on"]) == 1
        assert meta["workspace"] is True

    def test_plain_app_has_workspace(self, tmp_path):
        write_app_manifest(tmp_path / "app")
        meta = read_manifest(tmp_path / "app")
        assert meta["extends"] == []
        assert meta["workspace"] is True
