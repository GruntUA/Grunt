"""Security PoC: auth-flow tokens and emailed links.

* A challenge token (MFA verification / MFA enrollment), handed out after the
  password step but *before* the second factor, must not work as an access
  token - otherwise MFA is bypassed with the password alone.
* Links mailed to a user (password reset, email sign-in) must point at the
  configured site, never at an origin taken from the request headers - a
  forged ``Origin``/``Host`` would mail the victim a real token on the
  attacker's domain (reset poisoning -> account takeover).
"""

from __future__ import annotations

import pytest

from grunt.auth.doctypes.User.user import create_user
from grunt.auth.service import create_mfa_setup_token, create_mfa_token

M = "/api/v1/method/grunt.auth.doctypes.User.user"
EMAIL = "mfa-victim@grunt.example.com"


async def _user(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await create_user(EMAIL, "Str0ngPass-1", "Mfa", "Victim", None)
        await ctx.db._session().commit()
        from grunt.auth.doctypes.User.user import get_user_by_email

        return await get_user_by_email(EMAIL)


@pytest.mark.asyncio
@pytest.mark.parametrize("make", [create_mfa_token, create_mfa_setup_token])
async def test_challenge_token_is_not_an_access_token(ctx, client, make):
    user = await _user(ctx)
    token = make(user)
    r = await client.get(f"{M}.whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_reset_link_ignores_forged_origin(ctx, client, monkeypatch):
    await _user(ctx)
    sent: list[str] = []

    from grunt.email.service import email_service

    async def _capture(**kw):
        sent.append(kw.get("body") or "")

    monkeypatch.setattr(email_service, "queue_email", _capture)
    r = await client.post(
        f"{M}.forgot_password_api",
        json={"email": EMAIL},
        headers={"Origin": "https://evil.example", "Host": "evil.example"},
    )
    assert r.status_code == 200, r.text
    assert sent, "reset mail was not queued"
    assert "evil.example" not in sent[0]
