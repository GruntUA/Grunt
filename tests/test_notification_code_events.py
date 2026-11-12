"""Code events through standard Notification rules (NOTIFICATIONS_PLAN.md, step 3)."""

import pytest

from grunt.i18n import translation_service
from grunt.notification import events
from grunt.standard_records import apply_records, reset

ASSIGNEE = "assignee@grunt.example.com"
RULE = "Task assigned"

pytestmark = pytest.mark.usefixtures("standard_notifications")


async def _assign(ctx, description: str = "Перевірити звіт") -> None:
    await ctx.new_doc(
        "ToDo",
        {
            "description": description,
            "reference_doctype": "User",
            "reference_id": "someone@example.com",
            "assigned_to": ASSIGNEE,
            "status": "Open",
        },
    )


async def _bell(ctx, user: str = ASSIGNEE) -> list[dict]:
    return await ctx.db.get_all(
        "NotificationLog", filters={"user": user}, fields=["subject", "message", "notification"]
    )


@pytest.mark.asyncio
async def test_every_core_event_ships_a_standard_rule(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rules = await ctx.db.get_all(
            "Notification", filters={"event": "code"}, fields=["event_key", "is_standard"]
        )
    keys = {r["event_key"] for r in rules}
    assert keys == {e.key for e in events.list_events() if e.key.startswith("grunt.")}
    assert all(r["is_standard"] for r in rules)


@pytest.mark.asyncio
async def test_disabled_rule_sends_nothing(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.db.set_value("Notification", RULE, "is_enabled", False)
        await _assign(ctx)
        assert await _bell(ctx) == []


@pytest.mark.asyncio
async def test_reworded_rule_is_used_and_kept_by_migrate(ctx, monkeypatch):
    from grunt.config import settings

    monkeypatch.setattr(settings, "debug", False)  # a production site
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.save_doc("Notification", RULE, {"subject_template": "Нова задача: {{ target }}"})
        assert await ctx.db.get_value("Notification", RULE, "is_customized")

        # The app's files are applied again (grunt migrate): the edit stays.
        session = ctx.db._session()
        await apply_records("grunt", session, ctx.get_engine(), doctype="Notification")
        await _assign(ctx)
        assert [b["subject"] for b in await _bell(ctx)] == ["Нова задача: User someone@example.com"]

        # Reset to standard: the app's text again, following its updates.
        assert await reset("Notification", RULE)
        assert not await ctx.db.get_value("Notification", RULE, "is_customized")
        subject = await ctx.db.get_value("Notification", RULE, "subject_template")
    assert "Assigned to you" in subject


@pytest.mark.asyncio
async def test_rendered_in_each_recipients_language(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        for email, lang in ((ASSIGNEE, "en"), ("uk@grunt.example.com", "uk")):
            await ctx.new_doc(
                "User",
                {"email": email, "first_name": "Т", "last_name": "Т", "language": lang},
            )
        await _assign(ctx)
        await ctx.new_doc(
            "ToDo",
            {
                "description": "Перевірити звіт",
                "reference_doctype": "User",
                "reference_id": "someone@example.com",
                "assigned_to": "uk@grunt.example.com",
                "status": "Open",
            },
        )
        en = (await _bell(ctx))[0]["subject"]
        uk = (await _bell(ctx, "uk@grunt.example.com"))[0]["subject"]

    assert en.startswith("Assigned to you:")
    if "uk" in translation_service.ui_languages():
        assert uk != en


@pytest.mark.asyncio
async def test_unknown_event_and_no_rule_send_nothing(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        assert await events.trigger("nobody.listens", recipients=[ASSIGNEE]) == events.Triggered()
        assert await _bell(ctx) == []


@pytest.mark.asyncio
async def test_app_event_from_hooks(ctx, monkeypatch):
    from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext

    monkeypatch.setattr(events, "_events", dict(events._events))
    HOOK_CONSUMERS["notification_events"].apply(
        [{"key": "shop.order.paid", "label": "Order paid", "variables": ["amount"]}],
        LoadContext(app_name="shop", app_dir=__import__("pathlib").Path(__file__).parent),
    )
    assert events.get_event("shop.order.paid") is not None

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.new_doc(
            "Notification",
            {
                "event": "code",
                "event_key": "shop.order.paid",
                "recipients": [{"kind": "Event recipients"}],
                "channels": [{"channel": "in_app"}],
                "subject_template": "Оплачено {{ amount }}",
            },
        )
        sent = await events.trigger(
            "shop.order.paid", doc={"name": "O-1"}, recipients=[ASSIGNEE], extra={"amount": 120}
        )
        bell = await _bell(ctx)

    assert (sent.rules, sent.notified) == (1, 1)
    assert bell[0]["subject"] == "Оплачено 120"


@pytest.mark.asyncio
async def test_unknown_code_event_is_rejected(ctx):
    from fastapi import HTTPException

    from grunt.errors import ApplicationError

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        with pytest.raises((ApplicationError, HTTPException)):
            await ctx.new_doc(
                "Notification",
                {
                    "event": "code",
                    "event_key": "no.such.event",
                    "recipients": [{"kind": "Event recipients"}],
                    "channels": [{"channel": "in_app"}],
                },
            )


def test_extractor_reads_jinja_in_records():
    from pathlib import Path

    from grunt.i18n.extract import _scan_record_json

    records = Path(__file__).parents[1] / "grunt/notification/records/notification"
    found: set[str] = set()
    for name in ("task_assigned", "tasks_due"):
        path = records / name / f"{name}.json"

        def add(source, context, kind, origin, where, plural_source=""):
            found.add(source)

        _scan_record_json(path.read_text(), str(path), "grunt", add, {})
    assert "Assigned to you: %(target)s" in found
    assert "Reminder: %(count)d task with a due date" in found


@pytest.mark.asyncio
async def test_event_recipients_need_a_code_event(ctx):
    from fastapi import HTTPException

    from grunt.errors import ApplicationError

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        with pytest.raises((ApplicationError, HTTPException)):
            await ctx.new_doc(
                "Notification",
                {
                    "ref_doctype": "ToDo",
                    "event": "after_save",
                    "recipients": [{"kind": "Event recipients"}],
                    "channels": [{"channel": "in_app"}],
                },
            )


@pytest.mark.asyncio
async def test_a_failing_rule_does_not_stop_the_others(ctx, monkeypatch):
    from grunt.notification import rules

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.new_doc(
            "Notification",
            {
                "name": "Second",
                "event": "code",
                "event_key": "grunt.todo.assigned",
                "recipients": [{"kind": "Event recipients"}],
                "channels": [{"channel": "in_app"}],
                "subject_template": "{{ target }}",
            },
        )
        real_run = rules.run

        async def run(session, rule, *args, **kwargs):
            if rule["name"] == RULE:
                raise RuntimeError("boom")
            return await real_run(session, rule, *args, **kwargs)

        monkeypatch.setattr(rules, "run", run)
        result = await events.trigger(
            "grunt.todo.assigned",
            doc={"name": "T-1"},
            recipients=iter([ASSIGNEE]),  # an iterator: every rule still sees it
            extra={"target": "Задача", "note": "x"},
        )
        bell = await _bell(ctx)

    assert (result.rules, result.notified) == (1, 1)
    assert [b["subject"] for b in bell] == ["Задача"]


@pytest.mark.asyncio
async def test_reset_failure_keeps_the_edit_marked(ctx, monkeypatch):
    from grunt import standard_records

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.db.set_value("Notification", RULE, "is_customized", True)

        async def broken(*args, **kwargs):
            raise RuntimeError("bad file")

        monkeypatch.setattr(standard_records, "_apply_folder", broken)
        with pytest.raises(RuntimeError):
            await reset("Notification", RULE)
        assert await ctx.db.get_value("Notification", RULE, "is_customized")


@pytest.mark.asyncio
async def test_reminder_is_retried_when_no_channel_reaches_anyone(ctx, monkeypatch):
    from grunt.notification import channels
    from grunt.notification.channels import Outcome
    from grunt.tasks import reminders

    async def fail(self, session, recipient, message, *, delivery):
        return Outcome("Error", reason="down")

    monkeypatch.setattr(channels.InAppChannel, "send", fail)
    monkeypatch.setattr(channels.WebPushChannel, "send", fail)
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        row = {"name": "R-1", "owner": ASSIGNEE, "description": "Подзвонити"}
        await ctx.db.insert_one(
            "Reminder",
            {**row, "created_at": None, "remind_at": None, "notified": False},
        )
        assert await reminders.deliver(row) is False
        assert not await ctx.db.get_value("Reminder", "R-1", "notified")
