"""Sign-in policy (FRAPPE_GAP #20): password expiry, sessions per user, sign-in
hours and IPs per user, SSO only, and other sessions ended on a password change."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from httpx2 import AsyncClient

from grunt.site.settings import clear_settings_cache

_M = "/api/v1/method/grunt.auth"
_LOGIN = f"{_M}.user_api.login_api"
_CHANGE_EXPIRED = f"{_M}.user_api.change_expired_password_api"
_SET_PASSWORD = f"{_M}.user_api.set_user_password_api"

EMAIL = "policy@grunt.example.com"
PASSWORD = "Str0ngPass"


@pytest.fixture
async def account(ctx):
    from grunt.auth.users import create_user

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        user = await create_user(EMAIL, PASSWORD, "Pol", "Icy", None)
        await ctx.db._session().commit()
        return user.id


@asynccontextmanager
async def site(ctx, **values):
    """SystemSettings values for the block, back to the defaults after."""
    defaults = {
        "password_max_age_days": 0,
        "max_sessions_per_user": 0,
        "disable_password_login": False,
    }
    await ctx.db.set_value("SystemSettings", "SystemSettings", values)
    await ctx.db._session().commit()
    clear_settings_cache()
    try:
        yield
    finally:
        await ctx.db.set_value("SystemSettings", "SystemSettings", defaults)
        await ctx.db._session().commit()
        clear_settings_cache()


async def _login(client: AsyncClient, password: str = PASSWORD, ip: str = "203.0.113.7", device=""):
    headers = {"CF-Connecting-IP": ip}
    if device:
        headers["Cookie"] = f"grunt_device={device}"
    return await client.post(_LOGIN, json={"email": EMAIL, "password": password}, headers=headers)


async def _active_sessions(ctx, user_id: str) -> list[str]:
    return await ctx.db.get_all(
        "UserSession", filters={"user": user_id, "is_active": True}, pluck="name", limit=None
    )


@pytest.mark.asyncio
async def test_expired_password_is_changed_before_signing_in(ctx, client, account):
    async with site(ctx, password_max_age_days=30):
        old = datetime.now(UTC) - timedelta(days=31)
        await ctx.db.set_value("User", account, "password_changed_at", old)
        await ctx.db._session().commit()

        data = (await _login(client)).json()["data"]
        assert data["password_change_required"] and data["access_token"] is None
        token = data["password_change_token"]

        same = await client.post(
            _CHANGE_EXPIRED, json={"password_change_token": token, "new_password": PASSWORD}
        )
        assert same.status_code == 422, same.text  # must differ from the old one

        done = await client.post(
            _CHANGE_EXPIRED, json={"password_change_token": token, "new_password": "N3wStrongPass"}
        )
        assert done.status_code == 200, done.text
        assert done.json()["data"]["access_token"]
        changed = await ctx.db.get_value("User", account, "password_changed_at")
        assert changed and str(changed) > str(old)


@pytest.mark.asyncio
async def test_no_change_date_yet_starts_the_clock(ctx, client, account):
    async with site(ctx, password_max_age_days=30):
        await ctx.db.set_value("User", account, "password_changed_at", None)
        await ctx.db._session().commit()
        data = (await _login(client)).json()["data"]
        assert data["access_token"]  # not forced right after an update
        assert await ctx.db.get_value("User", account, "password_changed_at")


@pytest.mark.asyncio
async def test_a_new_session_ends_the_oldest_past_the_limit(ctx, client, account):
    async with site(ctx, max_sessions_per_user=1):
        await _login(client, device="phone")
        await ctx.db._session().commit()
        await _login(client, device="laptop")
        await ctx.db._session().commit()
        assert len(await _active_sessions(ctx, account)) == 1


@pytest.mark.asyncio
async def test_sign_in_hours_and_ips_per_user(ctx, client, account):
    await ctx.db.set_value("User", account, {"allowed_ips": "10.1.0.0/16"})
    await ctx.db._session().commit()
    assert (await _login(client, ip="203.0.113.7")).status_code == 403
    assert (await _login(client, ip="10.1.2.3")).status_code == 200

    now = datetime.now(UTC)
    # A one-minute window a few hours away from now, in any time zone.
    start = (now + timedelta(hours=6)).time().replace(second=0, microsecond=0)
    end = (now + timedelta(hours=6, minutes=1)).time().replace(second=0, microsecond=0)
    await ctx.db.set_value("User", account, {"login_after": start, "login_before": end})
    await ctx.db._session().commit()
    refused = await _login(client, ip="10.1.2.3")
    assert refused.status_code == 403
    assert start.strftime("%H:%M") in refused.text


@pytest.mark.asyncio
async def test_sso_only_spares_administrators(ctx, client, account):
    from grunt.auth.users import create_user

    # The account is the first user - System Manager; a second one is not.
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await create_user("plain@grunt.example.com", PASSWORD, "Pl", "Ain", None)
        await ctx.db._session().commit()
    async with site(ctx, disable_password_login=True):
        plain = await client.post(
            _LOGIN, json={"email": "plain@grunt.example.com", "password": PASSWORD}
        )
        assert plain.status_code == 403, plain.text
        assert (await _login(client)).status_code == 200  # the administrator


@pytest.mark.asyncio
async def test_changing_the_password_ends_the_other_sessions(ctx, client, account):
    other = (await _login(client, device="other")).json()["data"]
    me = (await _login(client, device="this")).json()["data"]
    await ctx.db._session().commit()
    assert len(await _active_sessions(ctx, account)) == 2

    resp = await client.post(
        _SET_PASSWORD,
        json={"user_id": account, "new_password": "An0therPass", "current_password": PASSWORD},
        headers={"Authorization": f"Bearer {me['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    await ctx.db._session().commit()
    assert len(await _active_sessions(ctx, account)) == 1
    assert other["access_token"] != me["access_token"]


async def _expired_challenge(ctx, client, account) -> str:
    old = datetime.now(UTC) - timedelta(days=31)
    await ctx.db.set_value("User", account, "password_changed_at", old)
    await ctx.db._session().commit()
    data = (await _login(client)).json()["data"]
    assert data["password_change_required"]
    return data["password_change_token"]


@pytest.mark.asyncio
async def test_a_password_change_challenge_works_once(ctx, client, account):
    async with site(ctx, password_max_age_days=30):
        token = await _expired_challenge(ctx, client, account)
        body = {"password_change_token": token, "new_password": "N3wStrongPass"}
        assert (await client.post(_CHANGE_EXPIRED, json=body)).status_code == 200
        again = await client.post(_CHANGE_EXPIRED, json={**body, "new_password": "Th1rdStrong"})
        assert again.status_code == 401


@pytest.mark.asyncio
async def test_a_challenge_is_void_after_another_change_or_sso_only(ctx, client, account):
    from grunt.auth.login_policy import mark_password_changed

    async with site(ctx, password_max_age_days=30):
        token = await _expired_challenge(ctx, client, account)
        # An admin (or a reset) changed the password meanwhile.
        async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
            await mark_password_changed(account)
        await ctx.db._session().commit()
        body = {"password_change_token": token, "new_password": "N3wStrongPass"}
        assert (await client.post(_CHANGE_EXPIRED, json=body)).status_code == 401

    from grunt.auth.users import create_user

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        plain = await create_user("plain2@grunt.example.com", PASSWORD, "Pl", "Ain", None)
        old = datetime.now(UTC) - timedelta(days=31)
        await ctx.db.set_value("User", plain.id, "password_changed_at", old)
        await ctx.db._session().commit()
    async with site(ctx, password_max_age_days=30):
        resp = await client.post(
            _LOGIN, json={"email": "plain2@grunt.example.com", "password": PASSWORD}
        )
        token = resp.json()["data"]["password_change_token"]
    async with site(ctx, disable_password_login=True):
        body = {"password_change_token": token, "new_password": "N3wStrongPass"}
        assert (await client.post(_CHANGE_EXPIRED, json=body)).status_code == 403
