"""Security PoC: a private file of one user must stay unreadable to another.

Each test plays the attacker (an ordinary signed-in user, no roles) against a
victim's private upload. A passing test means the attack is blocked.
"""

from urllib.parse import parse_qs, urlparse

import pytest

M = "/api/v1/method/grunt.storage.doctypes.File.file"
URL = f"{M}.get_content?file_id="


async def _login(client, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={"email": email, "password": "Secret-pass-123", "full_name": "Test User"},
    )
    assert r.status_code in (200, 201, 409), r.text
    r = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": email, "password": "Secret-pass-123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture
async def victim_file(client, auth_headers):
    """A private, unattached upload owned by the admin (the first user)."""
    up = await client.post(
        f"{M}.upload",
        files={"file": ("salary.txt", b"victim secret", "text/plain")},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    return parse_qs(urlparse(up.json()["data"]["url"]).query)["file_id"][0]


@pytest.fixture
async def attacker(client, auth_headers):
    return await _login(client, "attacker@grunt.example.com")


@pytest.mark.asyncio
async def test_file_get_list_hides_other_users_files(client, victim_file, attacker):
    r = await client.get(f"{M}.get_list", headers=attacker)
    assert r.status_code in (200, 403), r.text
    if r.status_code == 200:
        names = [i["name"] for i in r.json()["data"]["items"]]
        assert victim_file not in names


@pytest.mark.asyncio
async def test_response_does_not_sign_arbitrary_file_urls(client, victim_file, attacker):
    """Any JSON response echoing a get_content URL must not mint a signature for it."""
    me = "attacker@grunt.example.com"
    r = await client.put(
        f"/api/v1/docs/User/{me}", json={"bio": f"{URL}{victim_file}"}, headers=attacker
    )
    assert r.status_code == 200, r.text
    echoed = r.json()["data"]["bio"]
    if "&sig=" in echoed:
        stolen = await client.get(echoed)
        assert stolen.status_code != 200 or stolen.content != b"victim secret"
