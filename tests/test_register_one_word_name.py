"""Self-registration with a one-word name (a nickname) must satisfy User's
required ``last_name`` instead of failing validation."""

import pytest

_REGISTER = "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api"


@pytest.mark.asyncio
async def test_register_with_single_word_name(client):
    resp = await client.post(
        _REGISTER,
        json={"email": "nick@example.com", "password": "Secret-pass-123", "full_name": "Nick"},
    )
    assert resp.status_code == 200, resp.text
    login = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "nick@example.com", "password": "Secret-pass-123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["data"]["access_token"]
