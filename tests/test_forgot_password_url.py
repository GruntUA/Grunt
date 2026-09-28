"""The password-reset link is built from the caller's real origin
(Host / Origin / X-Forwarded-Proto), not the localhost APP_URL default."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from grunt.auth.doctypes.User import user as user_mod
from grunt.config import settings


class _StubURL:
    scheme = "http"


class _StubRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = Headers(headers)
        self.url = _StubURL()


class _User:
    id = "u1"
    full_name = "Тест Юзер"
    email = "u@example.com"
    language = None


@pytest.fixture
def _patched_user(monkeypatch):
    async def _get_user_by_email(email: str):
        return _User() if email == _User.email else None

    async def _make_token(user_id: str):
        return "TOK123"

    monkeypatch.setattr(user_mod, "get_user_by_email", _get_user_by_email)
    monkeypatch.setattr("grunt.auth.service.create_password_reset_token", _make_token)


async def _queued_bodies(ctx) -> tuple[str, str]:
    rows = await ctx.db.get_all(
        "EmailQueue",
        filters={"recipient": _User.email},
        fields=["content", "text_content"],
        limit=1,
    )
    assert rows, "no EmailQueue row was inserted"
    return rows[0]["content"], rows[0]["text_content"]


@pytest.mark.asyncio
async def test_reset_url_uses_request_origin(ctx, _patched_user):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "o@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        req = _StubRequest({"origin": "https://reset.example.com"})
        assert await user_mod.forgot_password_api(_User.email, request=req) is True

        html, text = await _queued_bodies(ctx)

    link = "https://reset.example.com/reset-password?token=TOK123"
    assert link in html
    assert link in text


@pytest.mark.asyncio
async def test_reset_url_uses_host_and_forwarded_proto(ctx, _patched_user):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "o@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        req = _StubRequest({"host": "dev2.itmlt.win", "x-forwarded-proto": "https"})
        assert await user_mod.forgot_password_api(_User.email, request=req) is True

        _, text = await _queued_bodies(ctx)

    assert "https://dev2.itmlt.win/reset-password?token=TOK123" in text


@pytest.mark.asyncio
async def test_reset_url_falls_back_to_app_url_without_request(ctx, _patched_user):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "o@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        assert await user_mod.forgot_password_api(_User.email, request=None) is True

        _, text = await _queued_bodies(ctx)

    base = settings.app_url.rstrip("/")
    assert f"{base}/reset-password?token=TOK123" in text


@pytest.mark.asyncio
async def test_endpoint_injects_request_into_method(client, ctx):
    """The /method dispatcher supplies `request` so the link uses the caller host."""
    await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={"email": "ep@example.com", "password": "secret", "full_name": "Ep User"},
    )
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "o@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

    r = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.forgot_password_api",
        json={"email": "ep@example.com"},
        headers={"origin": "https://portal.example"},
    )
    assert r.status_code == 200

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        rows = await ctx.db.get_all(
            "EmailQueue",
            filters={"recipient": "ep@example.com"},
            fields=["text_content"],
            limit=1,
        )
    assert rows
    assert "https://portal.example/reset-password?token=" in rows[0]["text_content"]
