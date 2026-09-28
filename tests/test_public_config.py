"""grunt.api.v1.site_config.get_public_config — guest-accessible SPA bootstrap."""

from __future__ import annotations

import pytest

from grunt.site.settings import clear_settings_cache

_METHOD = "/api/v1/method/grunt.api.v1.site_config.get_public_config"
_KEYS = {
    "app_name",
    "app_logo",
    "language",
    "languages",
    "timezone",
    "date_format",
    "allow_user_registration",
}


@pytest.mark.asyncio
async def test_public_config_is_guest_accessible_and_complete(client):
    resp = await client.post(_METHOD, json={})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == _KEYS
    # defaults from the permissive conftest seed
    assert isinstance(data["app_name"], str) and data["app_name"]
    assert data["allow_user_registration"] is True
    codes = {lang["code"] for lang in data["languages"]}
    assert {"en", "uk"} <= codes
    assert data["language"] in codes


@pytest.mark.asyncio
async def test_public_config_reflects_system_settings(ctx, client):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.db.set_value(
            "SystemSettings",
            "SystemSettings",
            {
                "app_name": "Реєстр громади",
                "date_format": "yyyy-mm-dd",
                "timezone": "UTC",
                "allow_user_registration": False,
            },
        )
        await ctx.db._session().commit()
    clear_settings_cache()

    data = (await client.post(_METHOD, json={})).json()["data"]
    assert data["app_name"] == "Реєстр громади"
    assert data["date_format"] == "yyyy-mm-dd"
    assert data["timezone"] == "UTC"
    assert data["allow_user_registration"] is False
