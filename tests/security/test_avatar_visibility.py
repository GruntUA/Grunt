"""F2 fix must not break cross-user avatar display: setting a File as a User's
avatar publishes that one file, so a *different* user can load it - while other
attachments on a User stay private (see test_signed_file_urls)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

M = "/api/v1/method/grunt.storage.doctypes.File.file"


async def _login(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={"email": email, "password": "Secret-pass-123", "full_name": "T U"},
    )
    r = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": email, "password": "Secret-pass-123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_avatar_becomes_public_and_visible_to_others(client, auth_headers):
    # Admin uploads a private file attached to their own User, then sets it
    # as their avatar.
    me = "admin@grunt.example.com"
    up = await client.post(
        f"{M}.upload",
        files={"file": ("face.png", b"AVATARBYTES", "image/png")},
        data={"attached_to_doctype": "User", "attached_to_id": me},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["url"]
    file_id = parse_qs(urlparse(url).query)["file_id"][0]
    bare = f"{M}.get_content?file_id={file_id}"

    # Before it's an avatar: private (no signature, no auth -> 401).
    assert (await client.get(bare)).status_code == 401

    r = await client.put(
        f"/api/v1/docs/User/{me}", json={"avatar": f"{M}.get_content?file_id={file_id}"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    # Now public: a different user (and even no user) can open it.
    other = await _login(client, "peer@grunt.example.com")
    assert (await client.get(bare, headers=other)).status_code == 200
    assert (await client.get(bare)).status_code == 200


@pytest.mark.asyncio
async def test_cannot_publish_another_users_file_via_own_avatar(client, auth_headers):
    """IDOR guard: setting your avatar to someone else's private file_id must
    NOT make that file public."""
    # Admin owns a private file.
    up = await client.post(
        f"{M}.upload",
        files={"file": ("victim.txt", b"victim-private", "text/plain")},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    victim_file = parse_qs(urlparse(up.json()["data"]["url"]).query)["file_id"][0]
    bare = f"{M}.get_content?file_id={victim_file}"

    # Attacker (a different user) points their own avatar at the victim's file.
    attacker = await _login(client, "idor@grunt.example.com")
    r = await client.put(
        f"/api/v1/docs/User/idor@grunt.example.com",
        json={"avatar": bare},
        headers=attacker,
    )
    assert r.status_code == 200, r.text

    # The victim's file must still be private: no token -> refused.
    assert (await client.get(bare)).status_code == 401
