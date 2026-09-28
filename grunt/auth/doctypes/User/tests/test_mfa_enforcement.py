"""``Role.require_mfa``: users holding such a role must enroll 2FA at sign-in
before any tokens are issued, and open sessions end on the next refresh."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyotp
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

M = "/api/v1/method/grunt.auth.doctypes.User.user"
EMAIL = "root@grunt.example.com"
PASSWORD = "Str0ngPass"


async def _bootstrap_admin(ctx) -> None:
    """First user → System Manager."""
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user(EMAIL, PASSWORD, "Root", "Admin", None)
        await ctx.db._session().commit()


async def _require_mfa_for_system_manager(ctx) -> None:
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        if await ctx.db.exists("Role", "System Manager"):
            await ctx.db.set_value("Role", "System Manager", "require_mfa", True)
        else:
            await ctx.new_doc("Role", {"role_name": "System Manager", "require_mfa": True})
        await ctx.db._session().commit()


async def _login(client: AsyncClient) -> dict:
    r = await client.post(f"{M}.login_api", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.mark.asyncio
async def test_login_forces_enrollment_then_signs_in(ctx, client: AsyncClient):
    await _bootstrap_admin(ctx)
    await _require_mfa_for_system_manager(ctx)

    data = await _login(client)
    assert data["access_token"] is None
    assert data["mfa_required"] is True
    assert data["mfa_setup_required"] is True
    token = data["mfa_token"]

    # A setup token is not an MFA-verification token.
    wrong_flow = await client.post(
        f"{M}.mfa_login_api", json={"mfa_token": token, "code": "123456"}
    )
    assert wrong_flow.status_code == 401

    begin = await client.post(f"{M}.mfa_enroll_begin", json={"mfa_token": token})
    assert begin.status_code == 200, begin.text
    secret = begin.json()["data"]["secret"]

    bad = await client.post(f"{M}.mfa_enroll_complete", json={"mfa_token": token, "code": "000000"})
    assert bad.status_code == 422

    done = await client.post(
        f"{M}.mfa_enroll_complete",
        json={"mfa_token": token, "code": pyotp.TOTP(secret).now()},
    )
    assert done.status_code == 200, done.text
    body = done.json()["data"]
    assert body["access_token"]
    assert body["backup_codes"]

    # Enrolled: the setup token is spent, the next login is a normal MFA challenge.
    again = await client.post(f"{M}.mfa_enroll_begin", json={"mfa_token": token})
    assert again.status_code == 401
    data = await _login(client)
    assert data["mfa_required"] is True
    assert not data.get("mfa_setup_required")


@pytest.mark.asyncio
async def test_mfa_token_cannot_be_used_for_enrollment(ctx, client: AsyncClient):
    from grunt.auth.doctypes.User.user import get_user_by_email
    from grunt.auth.service import create_mfa_token

    await _bootstrap_admin(ctx)
    await _require_mfa_for_system_manager(ctx)
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        user = await get_user_by_email(EMAIL)
    assert user is not None

    r = await client.post(f"{M}.mfa_enroll_begin", json={"mfa_token": create_mfa_token(user)})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_ends_session_once_role_requires_mfa(ctx, client: AsyncClient):
    await _bootstrap_admin(ctx)
    data = await _login(client)
    assert data["access_token"]

    await _require_mfa_for_system_manager(ctx)

    r = await client.post(f"{M}.refresh_api", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 401
