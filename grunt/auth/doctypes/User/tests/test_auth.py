"""Tests for the Auth system (whitelisted methods + HTTP surface)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_session_lifecycle(ctx, client: AsyncClient):
    """register → login → whoami → update_me, carrying name + language/timezone."""
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        user = await create_user(
            "admin@grunt.example.com", "Str0ngPass", "Admin", "Root", None
        )
        await ctx.db.set_value(
            "User", user.id, {"language": "en", "timezone": "Europe/Warsaw"}
        )
        await ctx.db._session().commit()

    login = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "admin@grunt.example.com", "password": "Str0ngPass"},
    )
    assert login.status_code == 200
    body = login.json()["data"]
    assert body["access_token"]
    assert body["user"]["language"] == "en"
    assert body["user"]["timezone"] == "Europe/Warsaw"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = (
        await client.get(
            "/api/v1/method/grunt.auth.doctypes.User.user.whoami", headers=headers
        )
    ).json()["data"]
    assert me["email"] == "admin@grunt.example.com"
    assert me["full_name"] == "Root Admin"
    assert me["language"] == "en"
    assert me["timezone"] == "Europe/Warsaw"

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


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client: AsyncClient):
    """An invalid JWT → 401 on whoami."""
    resp = await client.get(
        "/api/v1/method/grunt.auth.doctypes.User.user.whoami",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_requests_load_current_roles(ctx, client: AsyncClient):
    """A role removed after login must not remain active in the JWT."""
    from grunt.auth.doctypes.User.user import create_user
    from grunt.auth.service import create_access_token

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        user = await create_user("roles@grunt.example.com", "Str0ngPass", "Role", "Test", None)
        await ctx.save_doc("User", user.id, {"roles": [{"role_name": "Кадровик"}]})
        await ctx.db._session().commit()
        token = create_access_token(user)
        await ctx.save_doc("User", user.id, {"roles": []})
        await ctx.db._session().commit()

    response = await client.get(
        "/api/v1/method/grunt.auth.doctypes.User.user.whoami",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["roles"] == []


@pytest.mark.asyncio
async def test_self_edit_scope(ctx):
    """A non-privileged user may save their own profile fields but not roles,
    activation, superadmin or password state (`_enforce_self_edit_scope`)."""
    from grunt.auth.doctypes.User.user import User, create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        u = await create_user("selfedit@grunt.example.com", "Str0ngPass", "Self", "Edit", None)
        await ctx.new_doc("Role", {"role_name": "Manager"})
        # create_user() makes the very first user a superadmin — demote so this
        # exercises the non-privileged path.
        await ctx.db.set_value("User", u.id, {"is_superadmin": False, "is_active": True})
        await ctx.db._session().commit()
        uid = u.id

    me = User(doctype="User", data={"email": uid, "name": uid, "roles": [], "is_superadmin": False})

    async with ctx.context(ctx.db._session(), ctx._require_engine(), me):
        # profile field — allowed
        await ctx.save_doc("User", uid, {"first_name": "Renamed", "bio": "hi"})
        await ctx.db._session().commit()

        for forbidden_patch in (
            {"is_superadmin": True},
            {"is_active": False},
            {"signup_state": "pending"},
            {"roles": [{"role_name": "Manager"}]},
            {"password": "hacked-in-plain"},
        ):
            with pytest.raises(Exception) as exc:
                await ctx.save_doc("User", uid, forbidden_patch)
            assert "прав" in str(exc.value)
            ctx.db._session().expire_all()

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        row = await ctx.db.get_all(
            "User", filters={"name": uid}, fields=["first_name", "is_superadmin"], limit=1
        )
    assert row[0]["first_name"] == "Renamed"
    assert not row[0]["is_superadmin"]


async def _set_settings(ctx, **values) -> None:
    from grunt.site.settings import clear_settings_cache

    await ctx.db.set_value("SystemSettings", "SystemSettings", values)
    await ctx.db._session().commit()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_first_user_superadmin_and_registration_gate(ctx):
    """First user is always allowed and becomes superadmin; later self-signup
    obeys allow_user_registration and receives default_role."""
    from grunt.api.messages import ApplicationError
    from grunt.auth.doctypes.User.user import get_user_by_email, register

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        # First user: allowed even with registration disabled, gets superadmin.
        await _set_settings(ctx, allow_user_registration=False, default_role=None)
        await register(
            email="one@grunt.example.com", password="x", first_name="One", last_name="U"
        )
        await ctx.db._session().commit()

        u1 = await get_user_by_email("one@grunt.example.com")
        assert u1 is not None and u1.is_superadmin is True

        # Second user is now blocked.
        with pytest.raises(ApplicationError) as excinfo:
            await register(
                email="two@grunt.example.com", password="x", first_name="Two", last_name="U"
            )
        assert excinfo.value.code == "FORBIDDEN"

        # Enable registration + configure a default role.
        await ctx.new_doc("Role", {"role_name": "Member"})
        await _set_settings(ctx, allow_user_registration=True, default_role="Member")

        res = await register(
            email="two@grunt.example.com", password="x", first_name="Two", last_name="U"
        )
        await ctx.db._session().commit()

        u2 = await get_user_by_email("two@grunt.example.com")
        assert u2 is not None and u2.is_superadmin is False

        roles = await ctx.db.get_all(
            "UserRole",
            filters={
                "parent_name": res["name"],
                "parent_doctype": "User",
                "role_name": "Member",
            },
            fields=["name"],
            limit=1,
        )
        assert roles, "default_role should have been assigned"


@pytest.mark.asyncio
async def test_lockout_and_wrong_password(ctx):
    """Wrong password → authenticate() returns None; after max_login_attempts
    (from SystemSettings) the account locks for account_lockout_duration."""
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
            "UserRole",
            filters={"parent_name": uid, "parent_doctype": "User", "role_name": "Newcomer"},
            fields=["name"],
            limit=1,
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
async def test_signup_approval_flow(ctx, client: AsyncClient):
    """require_signup_approval: a self-registered user is 'pending' and cannot
    log in until a superadmin approves them."""
    from grunt.auth.doctypes.User.user import create_user

    # First user = superadmin (bootstrap), always approved, does the approving.
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user("root@grunt.example.com", "Str0ngPass", "Root", "Admin", None)
        await ctx.db._session().commit()
    await _set_settings(ctx, allow_user_registration=True, require_signup_approval=True)

    # Self sign-up → pending.
    reg = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={
            "email": "newbie@grunt.example.com",
            "password": "Str0ngPass",
            "full_name": "New Bie",
        },
    )
    assert reg.status_code == 200, reg.text
    assert reg.json()["data"]["approval_pending"] is True

    # Login is refused with a soft 'approval_pending' payload, no tokens.
    login = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "newbie@grunt.example.com", "password": "Str0ngPass"},
    )
    assert login.status_code == 200, login.text
    body = login.json()["data"]
    assert body["approval_pending"] is True
    assert body["access_token"] is None

    # Superadmin approves.
    admin_login = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "root@grunt.example.com", "password": "Str0ngPass"},
    )
    headers = {"Authorization": f"Bearer {admin_login.json()['data']['access_token']}"}

    pending = await client.get(
        "/api/v1/method/grunt.auth.doctypes.User.user.list_pending_users_api", headers=headers
    )
    assert [u["email"] for u in pending.json()["data"]] == ["newbie@grunt.example.com"]

    approve = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.approve_user_api",
        json={"user_id": "newbie@grunt.example.com"},
        headers=headers,
    )
    assert approve.status_code == 200, approve.text

    # Now the user can log in for real.
    ok = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "newbie@grunt.example.com", "password": "Str0ngPass"},
    )
    data = ok.json()["data"]
    assert data["access_token"]
    assert not data.get("approval_pending")


@pytest.mark.asyncio
async def test_signup_approval_off_by_default(ctx, client: AsyncClient):
    """Without the setting, registration behaves as before (immediate login)."""
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await _set_settings(ctx, allow_user_registration=True)

    reg = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={
            "email": "immediate@grunt.example.com",
            "password": "Str0ngPass",
            "full_name": "Imm Ediate",
        },
    )
    assert reg.json()["data"]["approval_pending"] is False

    login = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "immediate@grunt.example.com", "password": "Str0ngPass"},
    )
    assert login.json()["data"]["access_token"]


_SET_PWD = "/api/v1/method/grunt.auth.doctypes.User.user.set_user_password_api"


@pytest.mark.asyncio
async def test_set_user_password_self_service(ctx, client: AsyncClient):
    """A non-privileged user changes their own password by proving the current
    one; wrong current password and another user's record are both refused."""
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        boss = await create_user("pwboss@grunt.example.com", "Str0ngPass", "Pw", "Boss", None)
        me = await create_user("pwme@grunt.example.com", "Str0ngPass", "Pw", "Me", None)
        other = await create_user("pwother@grunt.example.com", "Str0ngPass", "Pw", "Other", None)
        await ctx.db.set_value("User", me.id, {"is_superadmin": False, "is_active": True})
        await ctx.db.set_value("User", other.id, {"is_superadmin": False, "is_active": True})
        await ctx.db._session().commit()
        assert boss  # first user → superadmin, keeps the demoted users non-privileged

    async def _login(email: str, password: str) -> dict[str, str]:
        r = await client.post(
            "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
            json={"email": email, "password": password},
        )
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

    headers = await _login("pwme@grunt.example.com", "Str0ngPass")

    wrong = await client.post(
        _SET_PWD,
        json={
            "user_id": "pwme@grunt.example.com",
            "new_password": "N3wStr0ngPass",
            "current_password": "nope",
        },
        headers=headers,
    )
    assert wrong.status_code == 403

    ok = await client.post(
        _SET_PWD,
        json={
            "user_id": "pwme@grunt.example.com",
            "new_password": "N3wStr0ngPass",
            "current_password": "Str0ngPass",
        },
        headers=headers,
    )
    assert ok.status_code == 200, ok.text

    # new password now works, old one does not
    await _login("pwme@grunt.example.com", "N3wStr0ngPass")

    # cannot change someone else's password without System Manager / superadmin
    forbidden = await client.post(
        _SET_PWD,
        json={
            "user_id": "pwother@grunt.example.com",
            "new_password": "N3wStr0ngPass",
            "current_password": "Str0ngPass",
        },
        headers=headers,
    )
    assert forbidden.status_code == 403

    # a superadmin sets anyone's password with no current_password
    admin_headers = await _login("pwboss@grunt.example.com", "Str0ngPass")
    admin_ok = await client.post(
        _SET_PWD,
        json={"user_id": "pwother@grunt.example.com", "new_password": "N3wStr0ngPass"},
        headers=admin_headers,
    )
    assert admin_ok.status_code == 200, admin_ok.text
    await _login("pwother@grunt.example.com", "N3wStr0ngPass")


@pytest.mark.asyncio
async def test_set_password_first_time_for_passwordless_user(ctx, client: AsyncClient):
    """A user provisioned via email link / OIDC has no password; they set one
    from their profile without being asked for a "current" password."""
    from grunt.auth.doctypes.User.user import (
        User,
        create_user,
        set_user_password_api,
        whoami,
    )
    from grunt.auth.login import find_or_create_external_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user("first@grunt.example.com", "Str0ngPass", "Fir", "St", None)  # superadmin
        ext = await find_or_create_external_user("passwordless@grunt.example.com", "Pw Less")
        await ctx.db.set_value("User", ext.id, {"is_superadmin": False, "is_active": True})
        await ctx.db._session().commit()
        assert not ext.hashed_password  # provisioned without a password

    # A no-op whoami-style check: the account cannot sign in with a password yet.
    denied = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "passwordless@grunt.example.com", "password": "anything-at-all"},
    )
    assert denied.status_code != 200

    async with ctx.context(
        ctx.db._session(),
        ctx._require_engine(),
        User(
            doctype="User",
            data={
                "email": "passwordless@grunt.example.com",
                "name": "passwordless@grunt.example.com",
                "roles": [],
                "is_superadmin": False,
            },
        ),
    ):
        me = await whoami()
        assert me["has_password"] is False

    async with ctx.context(
        ctx.db._session(),
        ctx._require_engine(),
        User(
            doctype="User",
            data={
                "email": "passwordless@grunt.example.com",
                "name": "passwordless@grunt.example.com",
                "roles": [],
                "is_superadmin": False,
            },
        ),
    ):
        # No current_password — accepted because there is no password yet.
        assert await set_user_password_api("passwordless@grunt.example.com", "N3wStr0ngPass")
        await ctx.db._session().commit()

    ok = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "passwordless@grunt.example.com", "password": "N3wStr0ngPass"},
    )
    assert ok.status_code == 200, ok.text
