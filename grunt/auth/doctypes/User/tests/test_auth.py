"""Tests for the Auth system (migrated to whitelisted methods)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_me(ctx, client: AsyncClient):
    """Full flow: register → login → whoami."""
    # Register via direct API
    u = await ctx.new_doc(
        "User",
        {
            "email": "admin@grunt.example.com",
            "password": "secret",
            "first_name": "Admin",
            "last_name": "Root",
        },
    )
    await ctx.db._session().commit()

    # Login (Keep HTTP to verify JWT generation)
    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "admin@grunt.example.com", "password": "secret"},
    )
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    assert token

    # whoami via whitelisted method directly
    from grunt.auth.doctypes.User.user import User as UserController
    from grunt.auth.doctypes.User.user import whoami

    # Wrap dict in controller to support attribute access in context
    u_obj = UserController(doctype="User", data=u)
    async with ctx.context(ctx.db._session(), ctx._require_engine(), u_obj):
        me = await whoami()
        assert me["email"] == "admin@grunt.example.com"
        assert me["full_name"] == "Root Admin"


@pytest.mark.asyncio
async def test_first_user_is_superadmin(ctx):
    """The first registered user gets is_superadmin=True."""
    from grunt.auth.doctypes.User.user import get_user_by_email, register

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        # First user
        await register(
            email="first@grunt.example.com",
            password="pass1",
            first_name="First",
            last_name="User",
        )
        await ctx.db._session().commit()

        u1 = await get_user_by_email("first@grunt.example.com")
        assert u1 is not None
        assert u1.is_superadmin is True

        # Second user
        await register(
            email="second@grunt.example.com",
            password="pass2",
            first_name="Second",
            last_name="User",
        )
        await ctx.db._session().commit()

        u2 = await get_user_by_email("second@grunt.example.com")
        assert u2 is not None
        assert u2.is_superadmin is False


@pytest.mark.asyncio
async def test_wrong_password_returns_401(ctx):
    """Incorrect password → authenticate() returns None."""
    from grunt.auth.doctypes.User.user import authenticate, create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user(
            "user@grunt.example.com",
            "correct",
            "Wrong",
            "Password",
            None,
        )
        await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine()):
        result = await authenticate("user@grunt.example.com", "wrong")
    assert result is None


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client: AsyncClient):
    """An invalid JWT → 401 on whoami."""
    resp = await client.get(
        "/api/v1/method/grunt.auth.doctypes.User.user.whoami",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


async def _set_settings(ctx, **values) -> None:
    from grunt.site.settings import clear_settings_cache

    await ctx.db.set_value("SystemSettings", "SystemSettings", values)
    await ctx.db._session().commit()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_lockout_uses_system_settings(ctx):
    """max_login_attempts / account_lockout_duration come from SystemSettings."""
    from grunt.auth.doctypes.User.user import authenticate, create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user("lock@grunt.example.com", "correct-horse", "Lock", "Me", None)
        await ctx.db._session().commit()

    await _set_settings(ctx, max_login_attempts=3, account_lockout_duration=15)

    async with ctx.context(ctx.db._session(), ctx._require_engine()):
        for _ in range(2):
            assert await authenticate("lock@grunt.example.com", "wrong") is None
        # 3rd failure trips the lock
        assert await authenticate("lock@grunt.example.com", "wrong") is None
        with pytest.raises(ValueError, match="locked"):
            await authenticate("lock@grunt.example.com", "correct-horse")

        row = (
            await ctx.db.get_all(
                "User",
                filters={"email": "lock@grunt.example.com"},
                fields=["locked_until"],
                limit=1,
            )
        )[0]
    assert row["locked_until"] is not None


@pytest.mark.asyncio
async def test_registration_gate_and_default_role(ctx):
    """allow_user_registration blocks self-signup (after the first user);
    default_role is granted to newcomers."""
    from grunt.api.messages import ApplicationError
    from grunt.auth.doctypes.User.user import register

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        # first user is always allowed, even with registration disabled
        await _set_settings(ctx, allow_user_registration=False, default_role=None)
        await register(email="one@grunt.example.com", password="x", first_name="One", last_name="U")
        await ctx.db._session().commit()

        # second user is now blocked
        with pytest.raises(ApplicationError) as excinfo:
            await register(
                email="two@grunt.example.com", password="x", first_name="Two", last_name="U"
            )
        assert excinfo.value.code == "FORBIDDEN"

        # enable + configure a default role
        await ctx.new_doc("Role", {"role_name": "Member"})
        await _set_settings(ctx, allow_user_registration=True, default_role="Member")

        res = await register(
            email="two@grunt.example.com", password="x", first_name="Two", last_name="U"
        )
        await ctx.db._session().commit()

        roles = await ctx.db.get_all(
            "UserRole",
            filters={"user_id": res["name"], "role_name": "Member"},
            fields=["name"],
            limit=1,
        )
        assert roles, "default_role should have been assigned"


@pytest.mark.asyncio
async def test_register_via_http_assigns_default_role(ctx, client: AsyncClient):
    """Guest-context registration (the real HTTP path) can still grant the
    admin-only default_role — _assign_default_role escalates to SYSTEM."""
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc("Role", {"role_name": "Newcomer"})
        await _set_settings(ctx, allow_user_registration=True, default_role="Newcomer")

    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={"email": "http@grunt.example.com", "password": "x", "full_name": "Http User"},
    )
    assert resp.status_code == 200, resp.text
    uid = resp.json()["data"]["id"]

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        rows = await ctx.db.get_all(
            "UserRole", filters={"user_id": uid, "role_name": "Newcomer"}, fields=["name"], limit=1
        )
    assert rows


@pytest.mark.asyncio
async def test_register_rejects_weak_password(ctx):
    """The register endpoint enforces the SystemSettings password policy."""
    from grunt.api.messages import ApplicationError
    from grunt.auth.doctypes.User.user import register

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await _set_settings(
            ctx,
            allow_user_registration=True,
            password_min_length=8,
            password_require_uppercase=True,
            password_require_numbers=True,
            password_require_lowercase=False,
            password_require_symbols=False,
        )
        with pytest.raises(ApplicationError) as excinfo:
            await register(
                email="weak@grunt.example.com",
                password="weak",
                first_name="Weak",
                last_name="Pw",
            )
        assert excinfo.value.code == "VALIDATION_ERROR"

        # a compliant password goes through
        await register(
            email="strong@grunt.example.com",
            password="Strong123",
            first_name="Strong",
            last_name="Pw",
        )


@pytest.mark.asyncio
async def test_whoami_and_update_me_carry_language_and_timezone(ctx, client: AsyncClient):
    """Per-user language/timezone round-trip: whoami exposes them, update_me sets them."""
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        user = await create_user("prefs@grunt.example.com", "Str0ngPass", "Pref", "S", None)
        await ctx.db.set_value(
            "User", user.id, {"language": "en", "timezone": "Europe/Warsaw"}
        )
        await ctx.db._session().commit()

    login = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "prefs@grunt.example.com", "password": "Str0ngPass"},
    )
    body = login.json()["data"]
    assert body["user"]["language"] == "en"
    assert body["user"]["timezone"] == "Europe/Warsaw"
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    me = await client.get(
        "/api/v1/method/grunt.auth.doctypes.User.user.whoami", headers=headers
    )
    assert me.json()["data"]["language"] == "en"
    assert me.json()["data"]["timezone"] == "Europe/Warsaw"

    upd = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.update_me_api",
        json={"language": "uk", "timezone": "UTC"},
        headers=headers,
    )
    assert upd.status_code == 200
    data = upd.json()["data"]
    assert data["language"] == "uk"
    assert data["timezone"] == "UTC"

    bad = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.update_me_api",
        json={"language": "de"},
        headers=headers,
    )
    assert bad.status_code == 422
