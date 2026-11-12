"""Notification channels and the delivery log (NOTIFICATIONS_PLAN.md, step 1).

Every notification goes through ``grunt.notification.delivery.deliver``: one
``NotificationDelivery`` row per recipient × channel; queued channels (email,
browser push) settle their row when the message finally goes out.
"""

import pytest

from grunt.notification import channels as channels_mod
from grunt.notification.channels import Channel, Message, Outcome, register_channel
from grunt.notification.delivery import deliver
from grunt.notification.service import notification_service

USER = "reader@example.com"


async def _deliveries(ctx, **filters) -> list[dict]:
    return await ctx.db.get_all(
        "NotificationDelivery",
        filters=filters,
        fields=[
            "name",
            "recipient",
            "channel",
            "status",
            "reason",
            "subject",
            "notification",
            "ref_doctype",
            "doc_id",
            "notification_log",
            "email_queue",
            "email_message",
        ],
        order_by="channel",
        order="asc",
        limit=50,
    )


async def _outgoing_account(ctx) -> None:
    await ctx.new_doc("EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True})


@pytest.mark.asyncio
async def test_notify_logs_every_channel(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _outgoing_account(ctx)
        session = ctx.db._session()
        log_id = await notification_service.notify(
            session,
            user=USER,
            doctype="User",
            doc_id="someone@example.com",
            subject="Призначено",
            message="Перевірити звіт",
            email=True,
        )
        rows = await _deliveries(ctx, recipient=USER)
        bell = await ctx.db.get_all("NotificationLog", filters={"user": USER}, fields=["name"])
        mails = await ctx.db.get_all("EmailQueue", filters={"recipient": USER}, fields=["name"])

    by_channel = {r["channel"]: r for r in rows}
    assert set(by_channel) == {"in_app", "web_push", "email"}
    assert by_channel["in_app"]["status"] == "Sent"
    assert by_channel["in_app"]["notification_log"] == log_id == bell[0]["name"]
    assert by_channel["web_push"]["status"] == "Queued"
    assert by_channel["email"]["status"] == "Queued"
    assert by_channel["email"]["email_queue"] == mails[0]["name"]
    for row in rows:
        assert row["subject"] == "Призначено"
        assert (row["ref_doctype"], row["doc_id"]) == ("User", "someone@example.com")


@pytest.mark.asyncio
async def test_email_only_rule_makes_no_bell_row(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _outgoing_account(ctx)
        rule = {
            "name": "rule-email",
            "channel": "email",
            "recipients": USER,
            "subject_template": "Новий {name}",
            "message_template": "",
        }
        sent = await notification_service.apply_rule(
            ctx.db._session(), rule, "User", {"name": "x@example.com"}, "actor@example.com", "x"
        )
        rows = await _deliveries(ctx, recipient=USER)
        bell = await ctx.db.get_all("NotificationLog", filters={"user": USER}, fields=["name"])

    assert sent == 1
    assert [(r["channel"], r["status"], r["notification"]) for r in rows] == [
        ("email", "Queued", "rule-email")
    ]
    assert rows[0]["subject"] == "Новий x@example.com"
    assert bell == []


@pytest.mark.asyncio
async def test_unknown_and_failing_channels_are_logged_others_still_go(ctx, monkeypatch):
    class Broken(Channel):
        name = "broken_test"
        label = "Broken"

        async def send(self, session, recipient, message, *, delivery):
            raise RuntimeError("gateway down")

    monkeypatch.setitem(channels_mod._channels, "broken_test", Broken())

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        report = await deliver(
            ctx.db._session(),
            [USER],
            Message(subject="Тест"),
            ["broken_test", "no_such_channel", "in_app"],
        )
        rows = {r["channel"]: r for r in await _deliveries(ctx, recipient=USER)}

    assert report.counts == {"Error": 1, "Skipped": 1, "Sent": 1}
    assert rows["broken_test"]["status"] == "Error"
    assert "gateway down" in rows["broken_test"]["reason"]
    assert rows["no_such_channel"]["status"] == "Skipped"
    assert rows["in_app"]["status"] == "Sent"


@pytest.mark.asyncio
async def test_email_queue_settles_the_delivery(ctx, monkeypatch):
    import conftest as _cf
    from grunt.email import tasks as email_tasks
    from grunt.email.service import EmailService

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _outgoing_account(ctx)
        await deliver(ctx.db._session(), [USER, "other@example.com"], Message("Лист"), ["email"])
        await ctx.db._session().commit()

    async def _fake_send_now(account, message):
        if message["recipient"] == "other@example.com":
            raise RuntimeError("mailbox full")
        return "EM-1"

    monkeypatch.setattr(EmailService, "send_now", staticmethod(_fake_send_now))
    monkeypatch.setattr(email_tasks.site_manager, "get_active_site", lambda: "test", raising=False)
    monkeypatch.setattr(
        email_tasks.site_manager,
        "get_session_maker",
        lambda _site: _cf.TestSessionLocal,
        raising=False,
    )
    monkeypatch.setattr(
        email_tasks.site_manager, "get_engine", lambda _site: _cf.test_engine, raising=False
    )
    await email_tasks.process_email_queue()

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        ok = (await _deliveries(ctx, recipient=USER))[0]
        failed = (await _deliveries(ctx, recipient="other@example.com"))[0]

    assert (ok["status"], ok["email_message"]) == ("Sent", "EM-1")
    assert failed["status"] == "Error"
    assert "mailbox full" in failed["reason"]


@pytest.mark.asyncio
async def test_push_without_subscription_is_skipped(ctx):
    from grunt.site.settings import clear_settings_cache
    from grunt.webpush.service import deliver_push

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await deliver(ctx.db._session(), [USER], Message("Пуш"), ["web_push"])
        row = (await _deliveries(ctx, recipient=USER))[0]
        assert row["status"] == "Queued"

        # Push switched off on the site: the sender says why it didn't go.
        await ctx.db.set_value("SystemSettings", "SystemSettings", {"enable_web_push": False})
        clear_settings_cache()
        await deliver_push(
            {"user": USER, "subject": "Пуш", "body": "", "url": "/", "delivery": row["name"]}
        )
        settled = (await _deliveries(ctx, recipient=USER))[0]

    assert settled["status"] == "Skipped"
    assert settled["reason"]


@pytest.mark.asyncio
async def test_app_channel_from_hooks(ctx, monkeypatch):
    from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext

    sent: list[tuple[str, str]] = []

    class Sms(Channel):
        name = "sms_test"
        label = "SMS"

        async def send(self, session, recipient, message, *, delivery):
            sent.append((recipient, message.subject))
            return Outcome("Sent")

    import sys
    import types

    module = types.ModuleType("fake_sms_app")
    module.Sms = Sms  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_sms_app", module)
    monkeypatch.setattr(channels_mod, "_channels", dict(channels_mod._channels))

    HOOK_CONSUMERS["notification_channels"].apply(
        ["fake_sms_app.Sms"], LoadContext(app_name="fake", app_dir=ctx_app_dir())
    )
    assert channels_mod.get_channel("sms_test") is not None
    assert "sms_test" in [o["value"] for o in channels_mod.channel_options()]

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await deliver(ctx.db._session(), [USER], Message("Код 1234"), ["sms_test"])
        rows = await _deliveries(ctx, recipient=USER)

    assert sent == [(USER, "Код 1234")]
    assert [(r["channel"], r["status"]) for r in rows] == [("sms_test", "Sent")]


def ctx_app_dir():
    from pathlib import Path

    return Path(__file__).parent


def test_register_channel_rejects_nameless():
    class Nameless(Channel):
        pass

    with pytest.raises(ValueError):
        register_channel(Nameless)
