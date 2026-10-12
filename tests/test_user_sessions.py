"""UserSession — one row per signed-in device, holding its refresh token."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
import pytest

from grunt.config import settings as cfg

if TYPE_CHECKING:
    from httpx2 import AsyncClient

_M = "/api/v1/method/grunt.auth.doctypes"
_LOGIN = f"{_M}.User.user.login_api"
_REFRESH = f"{_M}.User.user.refresh_api"
_LOGOUT = f"{_M}.User.user.logout_api"
_LIST = f"{_M}.UserSession.user_session.list_my_sessions"
_OTHERS = f"{_M}.UserSession.user_session.revoke_other_sessions"

EMAIL = "sess@grunt.example.com"
PASSWORD = "Str0ngPass"


@pytest.fixture
async def account(ctx):
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        user = await create_user(EMAIL, PASSWORD, "Sess", "Ion", None)
        await ctx.db._session().commit()
        return user.id


async def _login(
    client: AsyncClient,
    ua: str = "TestBrowser/1.0",
    device: str | None = None,
    ip: str = "203.0.113.7",
) -> dict:
    headers = {"User-Agent": ua, "CF-Connecting-IP": ip}
    if device:
        headers["Cookie"] = f"grunt_device={device}"
    resp = await client.post(_LOGIN, json={"email": EMAIL, "password": PASSWORD}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _refresh(client: AsyncClient, refresh_token: str):
    return await client.post(_REFRESH, json={"refresh_token": refresh_token})


def _sid(access_token: str) -> str:
    return jwt.decode(access_token, cfg.secret_key, algorithms=[cfg.algorithm])["sid"]


def _auth(data: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _session_row(ctx, sid: str) -> dict:
    rows = await ctx.db.get_all(
        "UserSession",
        filters={"name": sid},
        fields=["user", "ip_address", "user_agent", "is_active", "last_active_at"],
        limit=1,
    )
    return rows[0]


@pytest.mark.asyncio
async def test_login_opens_session_with_client_info(ctx, client: AsyncClient, account):
    data = await _login(client)
    row = await _session_row(ctx, _sid(data["access_token"]))
    assert row["user"] == account
    assert row["ip_address"] == "203.0.113.7"
    assert row["user_agent"] == "TestBrowser/1.0"
    assert row["is_active"]


@pytest.mark.asyncio
async def test_devices_do_not_kick_each_other(ctx, client: AsyncClient, account):
    first = await _login(client, ua="Laptop")
    second = await _login(client, ua="Phone")
    assert _sid(first["access_token"]) != _sid(second["access_token"])

    # The first device's refresh token still works after the second login.
    resp = await _refresh(client, first["refresh_token"])
    assert resp.status_code == 200, resp.text
    resp = await _refresh(client, second["refresh_token"])
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_keeps_session(ctx, client: AsyncClient, account):
    data = await _login(client)
    resp = await _refresh(client, data["refresh_token"])
    assert resp.status_code == 200, resp.text
    new = resp.json()["data"]

    assert _sid(new["access_token"]) == _sid(data["access_token"])
    assert new["refresh_token"] != data["refresh_token"]
    # The used token is single-use.
    assert (await _refresh(client, data["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_logout_ends_only_this_device(ctx, client: AsyncClient, account):
    laptop = await _login(client, ua="Laptop")
    phone = await _login(client, ua="Phone")

    resp = await client.post(_LOGOUT, headers=_auth(laptop))
    assert resp.status_code == 200, resp.text

    assert (await _refresh(client, laptop["refresh_token"])).status_code == 401
    assert (await _refresh(client, phone["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_idle_session_expires(ctx, client: AsyncClient, account):
    data = await _login(client)
    sid = _sid(data["access_token"])
    stale = datetime.now(UTC) - timedelta(days=2)
    await ctx.db.set_value("UserSession", sid, "last_active_at", stale)
    await ctx.db._session().commit()

    assert (await _refresh(client, data["refresh_token"])).status_code == 401

    # The next login closes the idle session.
    await _login(client)
    assert not (await _session_row(ctx, sid))["is_active"]


@pytest.mark.asyncio
async def test_list_and_revoke_other_sessions(ctx, client: AsyncClient, account):
    laptop = await _login(client, ua="Laptop")
    phone = await _login(client, ua="Phone")

    resp = await client.get(_LIST, headers=_auth(laptop))
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert len(rows) == 2
    assert [r["user_agent"] for r in rows if r["current"]] == ["Laptop"]

    resp = await client.post(_OTHERS, headers=_auth(laptop))
    assert resp.json()["data"] == 1
    assert (await _refresh(client, phone["refresh_token"])).status_code == 401
    assert (await _refresh(client, laptop["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_password_reset_ends_all_sessions(ctx, client: AsyncClient, account):
    from grunt.auth.service import consume_password_reset_token, create_password_reset_token

    data = await _login(client)
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        token = await create_password_reset_token(account)
        assert await consume_password_reset_token(token, "N3wPassword!")
        await ctx.db._session().commit()

    assert (await _refresh(client, data["refresh_token"])).status_code == 401


LAPTOP = "a" * 32
PHONE = "b" * 32


async def _logins(ctx, sid: str) -> list[dict]:
    return await ctx.db.get_all(
        "UserSessionLogin",
        filters={"parent_doctype": "UserSession", "parent_name": sid},
        fields=["ip_address", "method"],
        order_by="idx",
        order="asc",
        limit=None,
    )


@pytest.mark.asyncio
async def test_same_browser_reuses_its_session(ctx, client: AsyncClient, account):
    first = await _login(client, device=LAPTOP, ip="203.0.113.7")
    again = await _login(client, device=LAPTOP, ip="198.51.100.2")
    phone = await _login(client, device=PHONE)

    sid = _sid(first["access_token"])
    assert _sid(again["access_token"]) == sid
    assert _sid(phone["access_token"]) != sid
    assert await ctx.db.count("UserSession", {"user": account}) == 2

    assert (await _session_row(ctx, sid))["ip_address"] == "198.51.100.2"
    logins = await _logins(ctx, sid)
    assert [r["ip_address"] for r in logins] == ["203.0.113.7", "198.51.100.2"]
    assert {r["method"] for r in logins} == {"password"}

    # The device's earlier refresh token is replaced, the other device keeps its own.
    assert (await _refresh(client, first["refresh_token"])).status_code == 401
    assert (await _refresh(client, again["refresh_token"])).status_code == 200
    assert (await _refresh(client, phone["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_signed_out_browser_reopens_its_session(ctx, client: AsyncClient, account):
    first = await _login(client, device=LAPTOP)
    resp = await client.post(_LOGOUT, headers=_auth(first))
    assert resp.status_code == 200, resp.text

    again = await _login(client, device=LAPTOP)
    sid = _sid(again["access_token"])
    assert sid == _sid(first["access_token"])
    assert (await _session_row(ctx, sid))["is_active"]


@pytest.mark.asyncio
async def test_login_history_is_capped(ctx, client: AsyncClient, account):
    from grunt.site.settings import clear_settings_cache

    await ctx.db.set_value("SystemSettings", "SystemSettings", {"session_login_history": 2})
    await ctx.db._session().commit()
    clear_settings_cache()
    try:
        for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
            data = await _login(client, device=LAPTOP, ip=ip)
        rows = await _logins(ctx, _sid(data["access_token"]))
        assert [r["ip_address"] for r in rows] == ["10.0.0.2", "10.0.0.3"]
    finally:
        await ctx.db.set_value("SystemSettings", "SystemSettings", {"session_login_history": 20})
        await ctx.db._session().commit()
        clear_settings_cache()


@pytest.mark.asyncio
async def test_malformed_device_cookie_is_ignored(ctx, client: AsyncClient, account):
    first = await _login(client, device="not-a-device")
    second = await _login(client, device="not-a-device")
    assert _sid(first["access_token"]) != _sid(second["access_token"])


@pytest.mark.asyncio
async def test_idle_sessions_closed_for_everyone(ctx, client: AsyncClient, account):
    from grunt.auth.doctypes.UserSession.user_session import deactivate_expired

    data = await _login(client)
    sid = _sid(data["access_token"])
    await ctx.db.set_value(
        "UserSession", sid, "last_active_at", datetime.now(UTC) - timedelta(days=2)
    )
    await ctx.db._session().commit()

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        assert await deactivate_expired(None, 60) >= 1
    assert not (await _session_row(ctx, sid))["is_active"]
