"""Passwordless "sign in with email" provider — code + magic-link ceremony."""

from __future__ import annotations

import re

import pytest

_BEGIN = "/api/v1/auth/email/begin"
_COMPLETE = "/api/v1/auth/email/complete"
_METHODS = "/api/v1/auth/methods"


@pytest.fixture
def captured_mail(monkeypatch):
    """Swap the email queue for an in-memory sink so tests can read the code."""
    sent: list[dict] = []

    async def _fake_queue_email(session, to, subject, body, html_body=None):
        sent.append({"to": to, "subject": subject, "body": body, "html_body": html_body})
        return "queued-id"

    async def _fake_resolve(session):
        return "test-account"

    from grunt.email.service import EmailService, email_service

    monkeypatch.setattr(email_service, "queue_email", _fake_queue_email)
    monkeypatch.setattr(
        EmailService, "resolve_outgoing_account_id", staticmethod(_fake_resolve)
    )
    return sent


def _code_from(body: str) -> str:
    m = re.search(r"\b(\d{6})\b", body)
    assert m, body
    return m.group(1)


def _link_token_from(body: str) -> str:
    m = re.search(r"email_login_token=([\w.\-]+)", body)
    assert m, body
    return m.group(1)


@pytest.mark.asyncio
async def test_methods_endpoint_lists_email(client):
    resp = await client.get(_METHODS)
    assert resp.status_code == 200
    names = {m["name"]: m for m in resp.json()["data"]}
    assert "email" in names
    assert names["email"]["kind"] == "challenge"
    assert names["email"]["requires_identifier"] is True


@pytest.mark.asyncio
async def test_begin_rejects_invalid_email(client, captured_mail):
    resp = await client.post(_BEGIN, json={"email": "not-an-email"})
    assert resp.status_code == 422
    assert not captured_mail


@pytest.mark.asyncio
async def test_code_flow_signs_in_and_provisions_user(client, captured_mail):
    begin = await client.post(_BEGIN, json={"email": "Newby@grunt.example.com"})
    assert begin.status_code == 200, begin.text
    challenge_token = begin.json()["data"]["challenge_token"]

    assert len(captured_mail) == 1
    assert captured_mail[0]["to"] == "newby@grunt.example.com"  # normalised
    code = _code_from(captured_mail[0]["body"])

    resp = await client.post(
        _COMPLETE, json={"challenge_token": challenge_token, "code": code}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["user"]["email"] == "newby@grunt.example.com"


@pytest.mark.asyncio
async def test_wrong_code_is_rejected_but_does_not_burn_the_token(client, captured_mail):
    begin = await client.post(_BEGIN, json={"email": "someone@grunt.example.com"})
    challenge_token = begin.json()["data"]["challenge_token"]
    code = _code_from(captured_mail[0]["body"])

    bad = await client.post(
        _COMPLETE, json={"challenge_token": challenge_token, "code": "000001"}
    )
    assert bad.status_code == 401

    # A wrong guess must not invalidate the code — the real one still works.
    ok = await client.post(
        _COMPLETE, json={"challenge_token": challenge_token, "code": code}
    )
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_code_is_single_use(client, captured_mail):
    begin = await client.post(_BEGIN, json={"email": "once@grunt.example.com"})
    challenge_token = begin.json()["data"]["challenge_token"]
    code = _code_from(captured_mail[0]["body"])
    payload = {"challenge_token": challenge_token, "code": code}

    assert (await client.post(_COMPLETE, json=payload)).status_code == 200
    assert (await client.post(_COMPLETE, json=payload)).status_code == 401


@pytest.mark.asyncio
async def test_magic_link_is_single_use(client, captured_mail):
    await client.post(_BEGIN, json={"email": "onlink@grunt.example.com"})
    link_token = _link_token_from(captured_mail[0]["body"])

    assert (await client.post(_COMPLETE, json={"token": link_token})).status_code == 200
    assert (await client.post(_COMPLETE, json={"token": link_token})).status_code == 401


@pytest.mark.asyncio
async def test_link_is_dead_after_code_login(client, captured_mail):
    """Signing in with the code must kill the magic link from the same mail."""
    begin = await client.post(_BEGIN, json={"email": "both@grunt.example.com"})
    challenge_token = begin.json()["data"]["challenge_token"]
    body = captured_mail[0]["body"]
    code = _code_from(body)
    link_token = _link_token_from(body)

    used = await client.post(
        _COMPLETE, json={"challenge_token": challenge_token, "code": code}
    )
    assert used.status_code == 200, used.text

    dead = await client.post(_COMPLETE, json={"token": link_token})
    assert dead.status_code == 401


@pytest.mark.asyncio
async def test_new_request_invalidates_the_previous_code(client, captured_mail):
    r1 = await client.post(_BEGIN, json={"email": "rot@grunt.example.com"})
    old_challenge = r1.json()["data"]["challenge_token"]
    old_code = _code_from(captured_mail[0]["body"])

    r2 = await client.post(_BEGIN, json={"email": "rot@grunt.example.com"})
    new_challenge = r2.json()["data"]["challenge_token"]
    new_code = _code_from(captured_mail[1]["body"])

    # The first code's token row was dropped by the second request.
    stale = await client.post(
        _COMPLETE, json={"challenge_token": old_challenge, "code": old_code}
    )
    assert stale.status_code == 401

    fresh = await client.post(
        _COMPLETE, json={"challenge_token": new_challenge, "code": new_code}
    )
    assert fresh.status_code == 200, fresh.text


@pytest.mark.asyncio
async def test_challenge_token_without_code_is_not_enough(client, captured_mail):
    begin = await client.post(_BEGIN, json={"email": "x@grunt.example.com"})
    challenge_token = begin.json()["data"]["challenge_token"]

    resp = await client.post(_COMPLETE, json={"challenge_token": challenge_token})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_magic_link_flow_signs_in(client, captured_mail):
    await client.post(_BEGIN, json={"email": "linky@grunt.example.com"})
    link_token = _link_token_from(captured_mail[0]["body"])

    resp = await client.post(_COMPLETE, json={"token": link_token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["user"]["email"] == "linky@grunt.example.com"


@pytest.mark.asyncio
async def test_magic_link_points_at_request_origin_not_app_url(client, captured_mail):
    """The link must resolve to the host the user is actually on (reverse proxy),
    not the ``APP_URL`` default."""
    await client.post(
        _BEGIN,
        json={"email": "host@grunt.example.com"},
        headers={"origin": "https://dev2.example.com"},
    )
    assert (
        "https://dev2.example.com/login#email_login_token="
        in captured_mail[0]["body"]
    )


@pytest.mark.asyncio
async def test_existing_user_signs_in_without_registration(client, captured_mail, ctx):
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user("member@grunt.example.com", "Wh4tever", "Mem", "Ber", None)
        await ctx.db._session().commit()

    begin = await client.post(_BEGIN, json={"email": "member@grunt.example.com"})
    challenge_token = begin.json()["data"]["challenge_token"]
    code = _code_from(captured_mail[0]["body"])

    resp = await client.post(
        _COMPLETE, json={"challenge_token": challenge_token, "code": code}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["user"]["email"] == "member@grunt.example.com"


@pytest.mark.asyncio
async def test_begin_without_email_account_reports_unconfigured(client):
    """No mail sink patched, no EmailAccount seeded → a clear 422, not a silent pass."""
    resp = await client.post(_BEGIN, json={"email": "nowhere@grunt.example.com"})
    assert resp.status_code == 422
    assert "пошт" in resp.json()["error"]["message"].lower()
