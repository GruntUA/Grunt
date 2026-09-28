"""Tests for System Manager impersonation ("view as another user")."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

_START = "/api/v1/method/grunt.auth.doctypes.User.user.start_impersonation_api"
_STOP = "/api/v1/method/grunt.auth.doctypes.User.user.stop_impersonation_api"
_WHOAMI = "/api/v1/method/grunt.auth.doctypes.User.user.whoami"


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


@pytest.fixture
async def people(ctx):
    """First user → System Manager; plus a regular user and a second System Manager."""
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        boss = await create_user("boss@grunt.example.com", "Str0ngPass", "Boss", "Root", None)
        member = await create_user("member@grunt.example.com", "Str0ngPass", "Mem", "Ber", None)
        await ctx.save_doc("User", member.id, {"roles": [{"role_name": "Кадровик"}]})
        other_admin = await create_user("admin2@grunt.example.com", "Str0ngPass", "Ad", "Min", None)
        await ctx.save_doc("User", other_admin.id, {"roles": [{"role_name": "System Manager"}]})
        await ctx.db._session().commit()
        return {"boss": boss.id, "member": member.id, "other_admin": other_admin.id}


@pytest.mark.asyncio
async def test_system_manager_views_as_member(ctx, client: AsyncClient, people):
    token = await _login(client, "boss@grunt.example.com", "Str0ngPass")

    resp = await client.post(
        _START,
        json={"user_id": people["member"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["access_token"] and "refresh_token" not in data
    assert data["user"]["email"] == "member@grunt.example.com"
    assert data["impersonated_by"]["email"] == "boss@grunt.example.com"

    me = await client.get(_WHOAMI, headers={"Authorization": f"Bearer {data['access_token']}"})
    body = me.json()["data"]
    assert body["email"] == "member@grunt.example.com"
    assert body["roles"] == ["Кадровик"]
    assert body["impersonated_by"]["email"] == "boss@grunt.example.com"


@pytest.mark.asyncio
async def test_regular_user_cannot_impersonate(ctx, client: AsyncClient, people):
    token = await _login(client, "member@grunt.example.com", "Str0ngPass")
    resp = await client.post(
        _START,
        json={"user_id": people["boss"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_impersonate_system_manager_or_self(ctx, client: AsyncClient, people):
    token = await _login(client, "boss@grunt.example.com", "Str0ngPass")
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post(_START, json={"user_id": people["other_admin"]}, headers=headers)
    assert r1.status_code == 403

    r2 = await client.post(_START, json={"user_id": people["boss"]}, headers=headers)
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_stop_impersonation(ctx, client: AsyncClient, people):
    token = await _login(client, "boss@grunt.example.com", "Str0ngPass")
    start = await client.post(
        _START,
        json={"user_id": people["member"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    imp_token = start.json()["data"]["access_token"]

    stop = await client.post(_STOP, headers={"Authorization": f"Bearer {imp_token}"})
    assert stop.status_code == 200
    assert stop.json()["data"] is True
