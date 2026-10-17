"""enable_web_push in SystemSettings gates the Web Push surface."""

import pytest

from grunt.api.messages import ApplicationError
from grunt.site.settings import clear_settings_cache


async def _set_push(ctx, enabled: bool) -> None:
    await ctx.db.set_value("SystemSettings", "SystemSettings", {"enable_web_push": enabled})
    await ctx.db._session().commit()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_vapid_key_and_subscribe_blocked_when_disabled(ctx):
    from grunt.api.v1.notifications import get_vapid_public_key, subscribe_push

    async with ctx.context(ctx.db._session(), ctx.get_engine()):
        await _set_push(ctx, False)

        assert await get_vapid_public_key() is None

        with pytest.raises(ApplicationError) as excinfo:
            await subscribe_push("https://push.example/x", "p256", "auth")
        assert excinfo.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_send_push_early_returns_when_disabled(ctx):
    from grunt.webpush.service import webpush_service

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _set_push(ctx, False)

        await ctx.new_doc(
            "PushSubscription",
            {
                "user": "someone@example.com",
                "endpoint": "https://push.example/endpoint",
                "p256dh": "key",
                "auth": "secret",
            },
        )
        await ctx.db._session().commit()

        # Must not raise and must not attempt delivery — the disabled gate wins
        # before the (now correctly-argumented) subscription lookup.
        await webpush_service.send_push("someone@example.com", "Subject", "Body")


@pytest.mark.asyncio
async def test_test_action_reports_success_and_drops_expired(ctx, monkeypatch):
    import pywebpush
    from py_vapid import Vapid

    from grunt.actions.builtin import webpush_test
    from grunt.webpush.service import _generate_vapid_keys

    sent: list[dict] = []

    class _Resp:
        status_code = 201
        text = ""

    def fake_webpush(**kwargs):
        sent.append(kwargs)
        return _Resp()

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _set_push(ctx, True)
        await ctx.db.set_value(
            "SystemSettings", "SystemSettings", {"webpush_vapid_private": _generate_vapid_keys()[0]}
        )
        sub = await ctx.new_doc(
            "PushSubscription",
            {
                "user": "a@example.com",
                "endpoint": "https://push.example/e1",
                "p256dh": "k",
                "auth": "s",
            },
        )
        await ctx.db._session().commit()
        clear_settings_cache()

        res = await webpush_test(
            {"doctype": "PushSubscription", "name": sub["name"]},
            args={"title": "Hi", "body": "There", "url": "/app/home"},
        )
        assert res["message"]
        assert '"title": "Hi"' in sent[0]["data"] and "/app/home" in sent[0]["data"]
        # A parsed key, not the PEM string pywebpush can't read itself.
        assert isinstance(sent[0]["vapid_private_key"], Vapid)
        assert sent[0]["ttl"] > 0  # WNS rejects TTL 0

        class _Gone:
            status_code = 410
            text = "gone"

        def gone_webpush(**kwargs):
            raise pywebpush.WebPushException("gone", response=_Gone())

        monkeypatch.setattr(pywebpush, "webpush", gone_webpush)
        with pytest.raises(ApplicationError) as excinfo:
            await webpush_test({"doctype": "PushSubscription", "name": sub["name"]}, args={})
        assert excinfo.value.code == "PUSH_EXPIRED"
        assert not await ctx.db.exists("PushSubscription", sub["name"])


def test_send_to_user_action_is_admin_only():
    from grunt.actions.registry import get_doc_action

    spec = get_doc_action("webpush.send_to_user")
    assert spec is not None
    assert spec.doctypes == ["User"]
    assert spec.roles == ["System Manager"]


@pytest.mark.asyncio
async def test_send_to_user_action_pushes_every_browser(ctx, monkeypatch):
    import pywebpush

    from grunt.actions.builtin import webpush_send_to_user
    from grunt.webpush.service import _generate_vapid_keys

    sent: list[str] = []

    class _Resp:
        status_code = 201
        text = ""

    def fake_webpush(**kwargs):
        sent.append(kwargs["subscription_info"]["endpoint"])
        return _Resp()

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _set_push(ctx, True)
        await ctx.db.set_value(
            "SystemSettings", "SystemSettings", {"webpush_vapid_private": _generate_vapid_keys()[0]}
        )
        for i, user in enumerate(["b@example.com", "b@example.com", "other@example.com"]):
            await ctx.new_doc(
                "PushSubscription",
                {
                    "user": user,
                    "endpoint": f"https://push.example/u{i}",
                    "p256dh": "k",
                    "auth": "s",
                },
            )
        await ctx.db._session().commit()
        clear_settings_cache()

        res = await webpush_send_to_user(
            {"doctype": "User", "name": "b@example.com"}, args={"title": "Hello"}
        )
        assert sorted(sent) == ["https://push.example/u0", "https://push.example/u1"]
        assert "2" in res["message"]

        with pytest.raises(ApplicationError) as excinfo:
            await webpush_send_to_user(
                {"doctype": "User", "name": "nobody@example.com"}, args={"title": "Hello"}
            )
        assert excinfo.value.code == "NO_PUSH_SUBSCRIPTIONS"
