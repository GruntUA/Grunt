"""Role.allowed_ips: sign-in only from listed addresses; forwarded-IP headers are
trusted only from settings.trusted_proxies."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.requests import Request

from grunt.auth.doctypes.User.user import create_user
from grunt.auth.doctypes.UserSession.user_session import client_ip
from grunt.auth.ip_policy import ip_allowed, parse_ip_list

if TYPE_CHECKING:
    from httpx2 import AsyncClient

M = "/api/v1/method/grunt.auth.doctypes.User.user"
EMAIL = "root@grunt.example.com"
PASSWORD = "Str0ngPass"


def _request(peer: str, **headers: str) -> Request:
    return Request(
        {
            "type": "http",
            "client": (peer, 1234),
            "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()],
        }
    )


def test_parse_and_match():
    allowed = parse_ip_list("10.0.0.0/8, 192.168.1.5\n\n2001:db8::/32")
    assert allowed == {"10.0.0.0/8", "192.168.1.5", "2001:db8::/32"}
    assert ip_allowed("10.20.30.40", allowed)
    assert ip_allowed("192.168.1.5", allowed)
    assert ip_allowed("2001:db8::1", allowed)
    assert not ip_allowed("192.168.1.6", allowed)
    assert not ip_allowed(None, allowed)
    assert not ip_allowed("not-an-ip", allowed)


def test_forwarded_headers_trusted_only_from_proxy():
    # Behind the local proxy: the forwarded address is the client.
    assert client_ip(_request("127.0.0.1", cf_connecting_ip="10.1.2.3")) == "10.1.2.3"
    assert client_ip(_request("127.0.0.1", x_forwarded_for="10.9.9.9, 1.1.1.1")) == "10.9.9.9"
    assert client_ip(_request("127.0.0.1")) == "127.0.0.1"
    # Anyone else can't claim an address with a header.
    assert client_ip(_request("203.0.113.9", x_real_ip="10.1.2.3")) == "203.0.113.9"
    assert client_ip(_request("203.0.113.9", cf_connecting_ip="10.1.2.3")) == "203.0.113.9"
    # A Cloudflare edge is believed - but only for CF-Connecting-IP.
    assert client_ip(_request("104.23.162.181", cf_connecting_ip="10.1.2.3")) == "10.1.2.3"
    assert client_ip(_request("104.23.162.181", x_real_ip="10.1.2.3")) == "104.23.162.181"


async def _setup(ctx, allowed_ips: str) -> None:
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await create_user(EMAIL, PASSWORD, "Root", "Admin", None)  # -> System Manager
        if await ctx.db.exists("Role", "System Manager"):
            await ctx.db.set_value("Role", "System Manager", "allowed_ips", allowed_ips)
        else:
            await ctx.new_doc("Role", {"role_name": "System Manager", "allowed_ips": allowed_ips})
        await ctx.db._session().commit()


async def _login(client: AsyncClient, ip: str):
    return await client.post(
        f"{M}.login_api",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-Real-IP": ip},
    )


@pytest.mark.asyncio
async def test_sign_in_only_from_allowed_network(ctx, client: AsyncClient):
    await _setup(ctx, "10.0.0.0/8")

    assert (await _login(client, "203.0.113.9")).status_code == 403
    ok = await _login(client, "10.1.2.3")
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_refresh_from_disallowed_address_ends_session(ctx, client: AsyncClient):
    await _setup(ctx, "10.0.0.0/8")
    rt = (await _login(client, "10.1.2.3")).json()["data"]["refresh_token"]

    r = await client.post(
        f"{M}.refresh_api", json={"refresh_token": rt}, headers={"X-Real-IP": "203.0.113.9"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_restriction_by_default(ctx, client: AsyncClient):
    await _setup(ctx, "")
    assert (await _login(client, "203.0.113.9")).status_code == 200
