"""WebAuthn provider — registry wiring + a full (crypto-mocked) passkey ceremony."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

_METHODS = "/api/v1/auth/methods"


async def _access_token(ctx, client: AsyncClient, email: str = "pk@grunt.example.com") -> str:
    from grunt.auth.doctypes.User.user import create_user

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await create_user(email, "Str0ngPass", "Pass", "Key", None)
        await ctx.db._session().commit()

    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": email, "password": "Str0ngPass"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_methods_endpoint_lists_webauthn(client: AsyncClient):
    resp = await client.get(_METHODS)
    assert resp.status_code == 200
    names = {m["name"]: m for m in resp.json()["data"]}
    assert "webauthn" in names
    assert names["webauthn"]["kind"] == "challenge"
    assert names["webauthn"]["supports_enrollment"] is True


@pytest.mark.asyncio
async def test_unknown_provider_is_404(client: AsyncClient):
    resp = await client.post("/api/v1/auth/does-not-exist/begin", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_begin_authentication_returns_signed_challenge(client: AsyncClient):
    from grunt.auth.service import verify_challenge_token

    resp = await client.post("/api/v1/auth/webauthn/begin", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["options"]["challenge"]
    assert "rpId" in data["options"]

    claims = verify_challenge_token(data["challenge_token"], "webauthn-auth")
    assert claims and claims["challenge"] == data["options"]["challenge"]
    # rp_id / origin are derived from the request host and pinned into the token
    # so `complete` verifies against exactly what `begin` offered.
    assert claims["rp_id"] == data["options"]["rpId"] == "test"
    assert claims["origin"] == "http://test"
    # A token minted for one purpose can't be replayed into another.
    assert verify_challenge_token(data["challenge_token"], "webauthn-reg") is None


@pytest.mark.asyncio
async def test_cross_device_begin_is_discoverable_with_hybrid_hint(
    ctx, client: AsyncClient
):
    """`mode=cross-device` (sign in with a phone / QR) must be a discoverable
    request — never scoped to a credential list — and carry the hybrid hint."""
    await _access_token(ctx, client, "cd@grunt.example.com")  # user with no passkey

    resp = await client.post(
        "/api/v1/auth/webauthn/begin",
        json={"email": "cd@grunt.example.com", "mode": "cross-device"},
    )
    assert resp.status_code == 200, resp.text
    opts = resp.json()["data"]["options"]
    assert opts["hints"] == ["hybrid"]
    assert not opts.get("allowCredentials")


@pytest.mark.asyncio
async def test_cross_device_enroll_asks_for_a_roaming_authenticator(ctx, client: AsyncClient):
    """`mode=cross-device` enrolment forces cross-platform + the hybrid hint so
    the browser offers "phone (QR)" instead of "this Windows device"."""
    token = await _access_token(ctx, client, "enr@grunt.example.com")
    resp = await client.post(
        "/api/v1/auth/webauthn/enroll/begin",
        json={"mode": "cross-device"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    opts = resp.json()["data"]["options"]
    assert opts["hints"] == ["hybrid"]
    assert opts["authenticatorSelection"]["authenticatorAttachment"] == "cross-platform"


@pytest.mark.asyncio
async def test_oauth_callback_redirects_into_spa(client: AsyncClient):
    """A callback without a code bounces back to the SPA with an error fragment
    instead of rendering JSON in the address bar."""
    resp = await client.get(
        "/api/v1/oauth/google/callback", follow_redirects=False
    )
    assert resp.status_code == 302
    assert "/login#" in resp.headers["location"]
    assert "error=missing_code" in resp.headers["location"]


@pytest.mark.asyncio
async def test_full_passkey_register_then_login(ctx, client: AsyncClient, monkeypatch):
    """enroll → a WebAuthnCredential row → password-less sign-in, with the
    authenticator crypto stubbed out (no virtual authenticator in CI)."""
    import webauthn

    token = await _access_token(ctx, client)
    auth_headers = {"Authorization": f"Bearer {token}"}

    cred_id = b"\x01\x02\x03\x04fake-credential-id"
    pub_key = b"fake-public-key-bytes"

    class _Reg:
        credential_id = cred_id
        credential_public_key = pub_key
        sign_count = 0
        aaguid = "00000000-0000-0000-0000-000000000000"
        credential_backed_up = True

    monkeypatch.setattr(webauthn, "verify_registration_response", lambda **_: _Reg())

    # ── enrol ────────────────────────────────────────────────────────────
    begin = await client.post(
        "/api/v1/auth/webauthn/enroll/begin", json={}, headers=auth_headers
    )
    assert begin.status_code == 200, begin.text
    reg_challenge = begin.json()["data"]["challenge_token"]

    done = await client.post(
        "/api/v1/auth/webauthn/enroll/complete",
        json={
            "challenge_token": reg_challenge,
            "label": "Test Key",
            "response": {
                "id": "x",
                "rawId": "x",
                "type": "public-key",
                "response": {"transports": ["internal", "hybrid"]},
            },
        },
        headers=auth_headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["data"]["label"] == "Test Key"

    cred_b64 = webauthn.helpers.bytes_to_base64url(cred_id)
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        rows = await ctx.db.get_all(
            "WebAuthnCredential",
            filters={"credential_id": cred_b64},
            fields=["name", "user", "label", "transports", "backed_up"],
            limit=1,
        )
    assert rows and rows[0]["label"] == "Test Key"
    assert rows[0]["transports"] == "internal,hybrid"

    # enrolling the same authenticator again is rejected
    dup = await client.post(
        "/api/v1/auth/webauthn/enroll/complete",
        json={"challenge_token": reg_challenge, "response": {"id": "x", "rawId": "x"}},
        headers=auth_headers,
    )
    assert dup.status_code == 409

    # ── password-less sign-in ───────────────────────────────────────────
    class _Auth:
        new_sign_count = 5
        credential_backed_up = True

    monkeypatch.setattr(webauthn, "verify_authentication_response", lambda **_: _Auth())

    a_begin = await client.post(
        "/api/v1/auth/webauthn/begin", json={"email": "pk@grunt.example.com"}
    )
    assert a_begin.status_code == 200, a_begin.text
    a_data = a_begin.json()["data"]
    allowed = {c["id"] for c in a_data["options"]["allowCredentials"]}
    assert cred_b64 in allowed

    a_done = await client.post(
        "/api/v1/auth/webauthn/complete",
        json={
            "challenge_token": a_data["challenge_token"],
            "response": {
                "id": cred_b64,
                "rawId": cred_b64,
                "type": "public-key",
                "response": {
                    "clientDataJSON": "x",
                    "authenticatorData": "x",
                    "signature": "x",
                },
            },
        },
    )
    assert a_done.status_code == 200, a_done.text
    body = a_done.json()["data"]
    assert body["access_token"]
    assert body["user"]["email"] == "pk@grunt.example.com"
    assert body["mfa_required"] is False

    # sign_count advanced from the assertion
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        row = (
            await ctx.db.get_all(
                "WebAuthnCredential",
                filters={"credential_id": cred_b64},
                fields=["sign_count", "last_used_at"],
                limit=1,
            )
        )[0]
    assert row["sign_count"] == 5
    assert row["last_used_at"] is not None


@pytest.mark.asyncio
async def test_complete_rejects_expired_or_forged_challenge(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/webauthn/complete",
        json={"challenge_token": "not-a-real-token", "response": {"rawId": "abc"}},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enroll_requires_authentication(client: AsyncClient):
    resp = await client.post("/api/v1/auth/webauthn/enroll/begin", json={})
    assert resp.status_code == 401
