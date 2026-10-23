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
