"""Regression for the F2 fix: making signing authorization-aware must NOT stop
public files (e.g. avatars, website images) from being signed and served to
anyone - otherwise cross-user avatar display breaks."""

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
async def test_public_file_is_signed_and_openable_by_any_user(client, auth_headers):
    up = await client.post(
        f"{M}.upload",
        files={"file": ("logo.png", b"PNGDATA", "image/png")},
        data={"is_public": "true"},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["url"]
    # Public files need no signature to open, but when echoed through the API
    # they must still be servable to a different user.
    file_id = parse_qs(urlparse(url).query)["file_id"][0]
    other = await _login(client, "viewer@grunt.example.com")
    got = await client.get(f"{M}.get_content?file_id={file_id}", headers=other)
    assert got.status_code == 200
    assert got.content == b"PNGDATA"
