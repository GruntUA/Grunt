"""``@grunt.whitelist(session_cookie=True)``: a read-only GET signed in by the session cookie."""

import pytest
from httpx2 import AsyncClient

import grunt
from grunt.auth.session_cookie import SESSION_COOKIE, SIGNED_IN_COOKIE

_M = "/api/v1/method/grunt.auth.user_api"
_HERE = "/api/v1/method/tests.test_session_cookie_rpc"
EMAIL = "cookie@grunt.example.com"
PASSWORD = "Str0ngPass"


@grunt.whitelist(session_cookie=True)
async def cookie_whoami() -> str:
    return grunt.get_user().email


@grunt.whitelist()
async def bearer_whoami() -> str:
    return grunt.get_user().email


@pytest.fixture
async def session(ctx, client: AsyncClient) -> str:
    from grunt.auth.users import create_user

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await create_user(EMAIL, PASSWORD, "Cookie", "Jar", None)
        await ctx.db._session().commit()
    resp = await client.post(f"{_M}.login_api", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.cookies[SIGNED_IN_COOKIE] == "1"
    return resp.cookies[SESSION_COOKIE]


@pytest.mark.asyncio
async def test_get_signs_in_by_cookie(client: AsyncClient, session):
    resp = await client.get(f"{_HERE}.cookie_whoami")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == EMAIL


@pytest.mark.asyncio
async def test_post_ignores_cookie(client: AsyncClient, session):
    assert (await client.post(f"{_HERE}.cookie_whoami")).status_code == 401


@pytest.mark.asyncio
async def test_method_without_flag_ignores_cookie(client: AsyncClient, session):
    assert (await client.get(f"{_HERE}.bearer_whoami")).status_code == 401


@pytest.mark.asyncio
async def test_signed_out_cookie_is_refused(client: AsyncClient, session):
    resp = await client.post(f"{_M}.logout_api")
    assert resp.status_code == 200, resp.text
    # The jar dropped the cleared cookie; send the old value by hand.
    resp = await client.get(
        f"{_HERE}.cookie_whoami", headers={"Cookie": f"{SESSION_COOKIE}={session}"}
    )
    assert resp.status_code == 401
