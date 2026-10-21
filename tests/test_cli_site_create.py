"""``grunt site create`` writes a ``grunt.site`` the rest of the bench can read."""

import asyncio
import json

import dotenv
from click.testing import CliRunner

from grunt.cli import site as site_cli
from grunt.cli.site import site_create
from grunt.config import Settings


def test_site_create_writes_json_site_config(tmp_path, monkeypatch) -> None:
    (tmp_path / "apps").mkdir()
    (tmp_path / "sites").mkdir()
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(site_create, ["chat.example.test", "--no-migrate"])

    assert result.exit_code == 0, result.output
    config = json.loads((tmp_path / "sites" / "chat.example.test" / "grunt.site").read_text())
    assert config["installed_apps"] == ["grunt"]
    # every key in the site's .env must be a setting grunt knows (extra keys
    # make the settings model refuse to load)
    env = dotenv.dotenv_values(tmp_path / "sites" / "chat.example.test" / ".env")
    known = {name.upper() for name in Settings.model_fields}
    assert set(env) <= known, set(env) - known


def test_site_create_admin_passes_user_validation(monkeypatch) -> None:
    """The admin user must satisfy User's required name fields (last_name)."""
    captured: dict = {}

    async def fake_create_user(email, password, first_name, last_name, middle_name):
        captured.update(first_name=first_name, last_name=last_name)

    async def no_user(email):
        return None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def commit(self):
            pass

    monkeypatch.setattr(site_cli, "create_user", fake_create_user)
    monkeypatch.setattr(site_cli, "get_user_by_email", no_user)
    monkeypatch.setattr(site_cli.site_manager, "get_session_maker", lambda name: _Session)

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(site_cli.grunt, "context", lambda session: _Ctx())

    asyncio.run(site_cli._create_admin("chat.example.test", "a@b.c", "pw"))

    assert captured["first_name"] and captured["last_name"]
