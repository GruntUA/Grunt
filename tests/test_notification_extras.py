"""Notification rules, FRAPPE_GAP #10: email attachments and sender, a field
set after notifying, "N minutes before / after", the webhook channel."""

import json
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from grunt.metadata.compiler import OUTBOX_TABLE
from grunt.notification import rules as rules_mod
from grunt.notification.date_rules import moment_window, run_minute_rule
from tests.test_notification_rules import OWNER, _rule, _run, _ticket, tickets  # noqa: F401

# The ticket DocType, its users and an outgoing mailbox (test_notification_rules).
pytestmark = pytest.mark.usefixtures("tickets")

MEETING = {
    "name": "NotifMeeting",
    "label": "Meeting",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "starts_at", "label": "Starts", "fieldtype": "Datetime"},
        {"fieldname": "day", "label": "Day", "fieldtype": "Date"},
        {"fieldname": "reminded", "label": "Reminded", "fieldtype": "Check"},
    ],
}


async def _mail(ctx) -> list[dict]:
    return await ctx.db.get_all(
        "EmailQueue",
        filters={"recipient": OWNER},
        fields=["subject", "email_account", "attachments"],
        limit=None,
    )


def _attached(row: dict) -> list[str]:
    raw = row.get("attachments")
    items = json.loads(raw) if isinstance(raw, str) else raw or []
    return [a["filename"] for a in items]


@pytest.mark.asyncio
async def test_email_with_the_pdf_files_and_a_chosen_mailbox(ctx, monkeypatch):
    async def fake_pdf(html: str) -> bytes:
        return b"%PDF-1.4 " + html[:20].encode()

    monkeypatch.setattr(rules_mod, "html_to_pdf", fake_pdf)

    async def fake_render(doctype, doc, print_format=None):
        return f"<h1>{doc['title']}</h1>"

    monkeypatch.setattr(rules_mod, "render_print_html", fake_render)

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        account = await ctx.new_doc(
            "EmailAccount", {"email_address": "sales@grunt.example.com", "enable_outgoing": True}
        )
        from grunt.storage.files import store

        await store(
            b"hello",
            "note.txt",
            "text/plain",
            attached_to_doctype="NotifTicket",
            attached_to_id="T-1",
        )
        rule = await _rule(
            ctx,
            channels=[{"channel": "email"}],
            attach_print=True,
            attach_files=True,
            email_account=account["name"],
        )
        assert await _run(ctx, rule, await _ticket(ctx)) == 1
        mail = await _mail(ctx)

    assert len(mail) == 1
    assert mail[0]["email_account"] == account["name"]
    assert _attached(mail[0]) == ["T-1.pdf", "note.txt"]


@pytest.mark.asyncio
async def test_webhook_goes_once_per_notification(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        hook = await ctx.new_doc(
            "OutgoingWebhook",
            {"event": "notification", "url": "https://hooks.example.com/x", "is_enabled": True},
        )
        rule = await _rule(
            ctx,
            recipients=[{"kind": "Author"}, {"kind": "Document field", "field": "client"}],
            channels=[{"channel": "in_app"}, {"channel": "webhook", "webhook": hook["name"]}],
        )
        await _run(ctx, rule, await _ticket(ctx))
        rows = (
            await ctx.db._session().execute(
                sa.select(OUTBOX_TABLE.c.payload).where(
                    OUTBOX_TABLE.c.handler.like("%deliver_webhook")
                )
            )
        ).all()

    assert len(rows) == 1
    body = json.loads(rows[0][0]["body"])
    assert body["subject"] == "Зламався принтер" and body["recipients"] == 2


@pytest.mark.asyncio
async def test_webhook_channel_needs_a_webhook(ctx):
    from fastapi import HTTPException

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        with pytest.raises(HTTPException):
            await _rule(ctx, channels=[{"channel": "webhook"}])


@pytest.mark.asyncio
async def test_minutes_before_and_set_field_after(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**MEETING, "__is_new": True})
    await ctx.db._session().commit()
    now = datetime.now(UTC)
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        soon = await ctx.new_doc(
            "NotifMeeting", {"title": "Нарада", "starts_at": now + timedelta(minutes=27)}
        )
        await ctx.new_doc(
            "NotifMeeting", {"title": "Пізніше", "starts_at": now + timedelta(minutes=90)}
        )
        rule = await _rule(
            ctx,
            ref_doctype="NotifMeeting",
            event="minutes_before",
            date_field="starts_at",
            minutes=30,
            set_field="reminded",
            set_value="1",
        )
        await ctx.db._session().commit()
        rule_row = (await ctx.db.get_all("Notification", filters={"name": rule["name"]}))[0]

        # Its moment (starts - 30 min) fell within the last window: 09:57.
        start, end = moment_window(rule_row, now)
        assert start < now + timedelta(minutes=27) <= end
        assert await run_minute_rule(rule_row, now) == 1
        assert await run_minute_rule(rule_row, now + timedelta(minutes=5)) == 0  # once
        reminded = await ctx.db.get_value("NotifMeeting", soon["name"], "reminded")

    assert reminded


@pytest.mark.asyncio
async def test_minute_rules_need_a_datetime_field(ctx):
    from fastapi import HTTPException

    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**MEETING, "name": "NotifMeeting2", "__is_new": True})
    await ctx.db._session().commit()
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        with pytest.raises(HTTPException):
            await _rule(
                ctx, ref_doctype="NotifMeeting2", event="minutes_after", date_field="day", minutes=5
            )
        with pytest.raises(HTTPException):
            await _rule(ctx, set_field="no_such_field", set_value="x")
