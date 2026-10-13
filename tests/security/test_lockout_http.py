"""Security PoC: failed sign-in attempts must be counted through the real HTTP
path. The endpoint raises after recording a failure, and the request session is
rolled back on an exception - a counter written in that same transaction would
be undone, leaving password and MFA guessing unlimited."""

from __future__ import annotations

import pytest

from grunt.auth.doctypes.User.user import create_user

M = "/api/v1/method/grunt.auth.doctypes.User.user"
EMAIL = "lockme@grunt.example.com"


async def _setup(ctx, attempts: int = 3):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await create_user(EMAIL, "Correct-horse-1", "Lock", "Me", None)
    await ctx.db._session().commit()
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.save_doc(
            "SystemSettings",
            "SystemSettings",
            {"max_login_attempts": attempts, "account_lockout_duration": 15},
        )
        await ctx.db._session().commit()
    from grunt.site.settings import clear_settings_cache

    clear_settings_cache()


@pytest.mark.asyncio
async def test_password_failures_lock_the_account_over_http(ctx, client):
    await _setup(ctx)
    for _ in range(3):
        r = await client.post(f"{M}.login_api", json={"email": EMAIL, "password": "wrong"})
        assert r.status_code in (401, 429)
    # Even the right password is refused once locked.
    r = await client.post(f"{M}.login_api", json={"email": EMAIL, "password": "Correct-horse-1"})
    assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_wrong_mfa_codes_lock_the_account(ctx, client):
    import pyotp

    from grunt.auth.service import create_mfa_token

    await _setup(ctx)
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        from grunt.auth.doctypes.User.user import get_user_by_email

        await ctx.db.set_value(
            "User", EMAIL, {"mfa_enabled": True, "mfa_secret": pyotp.random_base32()}
        )
        await ctx.db._session().commit()
        user = await get_user_by_email(EMAIL)
    assert user is not None
    token = create_mfa_token(user)
    for _ in range(3):
        r = await client.post(f"{M}.mfa_login_api", json={"mfa_token": token, "code": "000000"})
        assert r.status_code in (401, 429)
    r = await client.post(f"{M}.mfa_login_api", json={"mfa_token": token, "code": "000000"})
    assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_mfa_lockout_not_reset_by_re_entering_password(ctx, client):
    """The MFA-code counter must not be wiped by a fresh password login - else a
    known password lets an attacker reset the lockout and brute-force the code."""
    import pyotp

    await _setup(ctx)
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.db.set_value(
            "User", EMAIL, {"mfa_enabled": True, "mfa_secret": pyotp.random_base32()}
        )
        await ctx.db._session().commit()

    # Alternate: password login (would previously clear the counter) then a
    # wrong MFA code. After enough wrong codes the account must lock despite the
    # interleaved successful password steps.
    locked = False
    for _ in range(5):
        pw = await client.post(
            f"{M}.login_api", json={"email": EMAIL, "password": "Correct-horse-1"}
        )
        if pw.status_code == 429:
            locked = True
            break
        token = pw.json()["data"]["mfa_token"]
        code = await client.post(f"{M}.mfa_login_api", json={"mfa_token": token, "code": "000000"})
        if code.status_code == 429:
            locked = True
            break
    assert locked, "account never locked despite repeated wrong MFA codes"


@pytest.mark.asyncio
async def test_disabled_account_gets_no_tokens(ctx, client):
    """A disabled user with the right password must be refused at sign-in, not
    handed tokens that every following request rejects with 401."""
    await _setup(ctx)
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.db.set_value("User", EMAIL, "is_active", False)
        await ctx.db._session().commit()
    r = await client.post(f"{M}.login_api", json={"email": EMAIL, "password": "Correct-horse-1"})
    assert r.status_code == 401, r.text
    assert "access_token" not in r.text
