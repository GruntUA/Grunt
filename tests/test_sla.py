"""Service levels - deadline arithmetic, clock tracking, warnings and escalation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

from grunt import _
from grunt.errors import ApplicationError
from grunt.notification import sla

# ── Deadline arithmetic ──────────────────────────────────────────────────


def test_deadline_units():
    tz = sla._tz()
    friday_noon = datetime(2026, 10, 9, 12, 0, tzinfo=tz).astimezone(UTC)

    assert sla.deadline(friday_noon, 5, "Hours") == friday_noon + timedelta(hours=5)

    two_days = sla.deadline(friday_noon, 2, "Days").astimezone(tz)
    assert (two_days.date(), two_days.hour, two_days.minute) == (date(2026, 10, 11), 23, 59)

    # Friday + 1 working day -> Monday; + 3 -> Wednesday.
    assert sla.deadline(friday_noon, 1, "Working days").astimezone(tz).date() == date(2026, 10, 12)
    assert sla.deadline(friday_noon, 3, "Working days").astimezone(tz).date() == date(2026, 10, 14)


def test_dates_are_local_days():
    tz = sla._tz()
    start = sla.as_datetime("2026-10-15")
    end = sla.as_datetime(date(2026, 10, 15), end_of_day=True)
    assert start is not None and end is not None
    assert start.astimezone(tz).isoformat() == "2026-10-15T00:00:00+03:00"
    assert end.astimezone(tz).strftime("%Y-%m-%d %H:%M") == "2026-10-15 23:59"
    assert sla.as_datetime(None) is None


# ── Tracking ─────────────────────────────────────────────────────────────

TICKET = {
    "name": "SlaTicket",
    "label": "SLA Ticket",
    "module": "core",
    "status_field": "status",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Open\nIn progress\nClosed",
            "default": "Open",
        },
        {
            "fieldname": "priority",
            "label": "Priority",
            "fieldtype": "Select",
            "options": "Normal\nLow",
        },
        {"fieldname": "due", "label": "Due", "fieldtype": "Date"},
        {"fieldname": "assignee", "label": "Assignee", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True}
    ],
}

ASSIGNEE = "worker@grunt.example.com"
BOSS = "boss@grunt.example.com"


@pytest.fixture
async def policy(ctx):
    from grunt.api.v1.meta import save_doctype

    sla.invalidate()
    await save_doctype(doctype_data={**TICKET, "__is_new": True})
    doc = await ctx.new_doc(
        "ServiceLevel",
        {
            "title": "Tickets in 2 days",
            "ref_doctype": "SlaTicket",
            "condition": "doc.get('priority') != 'Low'",
            "target": 2,
            "target_unit": "Days",
            "due_field": "due",
            "warn_before": 24,
            "done_states": "Closed",
            "notify": "{field:assignee}",
            "escalate_to": BOSS,
        },
    )
    await ctx.db._session().commit()
    yield doc
    sla.invalidate()


async def _status(ctx, ticket):
    rows = await ctx.db.get_all(
        "ServiceLevelStatus", filters={"ref_doctype": "SlaTicket", "ref_name": ticket}, limit=5
    )
    return rows[0] if rows else None


async def _notified(ctx, user):
    rows = await ctx.db.get_all("Notification", filters={"user": user}, fields=["subject"])
    return [r["subject"] for r in rows]


@pytest.mark.asyncio
async def test_clock_starts_and_fills_deadline(ctx, policy):
    t = await ctx.new_doc("SlaTicket", {"title": "Printer", "assignee": ASSIGNEE})
    row = await _status(ctx, t["name"])
    assert row is not None
    assert row["status"] == "On track"
    assert row["service_level"] == "Tickets in 2 days"

    due = sla.as_datetime(row["due_at"])
    assert due is not None
    local_due = due.astimezone(sla._tz()).date()
    stored = await ctx.db.get_value("SlaTicket", t["name"], "due")
    assert str(stored)[:10] == local_due.isoformat()
    assert local_due == datetime.now(sla._tz()).date() + timedelta(days=2)


@pytest.mark.asyncio
async def test_condition_and_done_documents_are_skipped(ctx, policy):
    low = await ctx.new_doc("SlaTicket", {"title": "Low", "priority": "Low"})
    closed = await ctx.new_doc("SlaTicket", {"title": "Done", "status": "Closed"})
    assert await _status(ctx, low["name"]) is None
    assert await _status(ctx, closed["name"]) is None


@pytest.mark.asyncio
async def test_done_stops_the_clock(ctx, policy):
    t = await ctx.new_doc("SlaTicket", {"title": "Mouse"})
    await ctx.save_doc("SlaTicket", t["name"], {"status": "In progress"})
    assert (await _status(ctx, t["name"]))["status"] == "On track"

    await ctx.save_doc("SlaTicket", t["name"], {"status": "Closed"})
    row = await _status(ctx, t["name"])
    assert row["status"] == "Met"
    assert row["met_at"]

    # Reopening does not restart a finished clock.
    await ctx.save_doc("SlaTicket", t["name"], {"status": "Open"})
    assert (await _status(ctx, t["name"]))["status"] == "Met"


@pytest.mark.asyncio
async def test_hand_set_deadline_moves_the_clock(ctx, policy):
    t = await ctx.new_doc("SlaTicket", {"title": "Server", "due": "2026-12-31"})
    row = await _status(ctx, t["name"])
    assert sla.as_datetime(row["due_at"]).astimezone(sla._tz()).date() == date(2026, 12, 31)

    await ctx.save_doc("SlaTicket", t["name"], {"due": "2027-01-15"})
    row = await _status(ctx, t["name"])
    assert sla.as_datetime(row["due_at"]).astimezone(sla._tz()).date() == date(2027, 1, 15)


@pytest.mark.asyncio
async def test_warning_then_breach_with_escalation(ctx, policy):
    t = await ctx.new_doc("SlaTicket", {"title": "Network", "assignee": ASSIGNEE})
    due = sla.as_datetime((await _status(ctx, t["name"]))["due_at"])

    assert await sla.process_deadlines(due - timedelta(hours=48)) == {"warned": 0, "breached": 0}

    assert await sla.process_deadlines(due - timedelta(hours=12)) == {"warned": 1, "breached": 0}
    row = await _status(ctx, t["name"])
    assert row["status"] == "At risk" and row["warned_at"]
    params = {"doctype": _("SlaTicket"), "name": t["name"]}
    warned = _("Deadline approaching: %(doctype)s %(name)s") % params
    missed = _("Deadline missed: %(doctype)s %(name)s") % params
    assert await _notified(ctx, ASSIGNEE) == [warned]
    assert await _notified(ctx, BOSS) == []

    # Same state on the next tick -> no repeat notification.
    assert await sla.process_deadlines(due - timedelta(hours=11)) == {"warned": 0, "breached": 0}

    assert await sla.process_deadlines(due + timedelta(hours=1)) == {"warned": 0, "breached": 1}
    row = await _status(ctx, t["name"])
    assert row["status"] == "Breached" and row["breached_at"]
    assert await _notified(ctx, BOSS) == [missed]
    assert sorted(await _notified(ctx, ASSIGNEE)) == sorted([warned, missed])

    # Closing after the deadline -> "Met late".
    await ctx.save_doc("SlaTicket", t["name"], {"status": "Closed"})
    assert (await _status(ctx, t["name"]))["status"] == "Met late"


@pytest.mark.asyncio
async def test_delete_drops_tracking(ctx, policy):
    t = await ctx.new_doc("SlaTicket", {"title": "Temp"})
    assert await _status(ctx, t["name"]) is not None
    await ctx.delete_doc("SlaTicket", t["name"])
    assert await _status(ctx, t["name"]) is None


@pytest.mark.asyncio
async def test_policy_validation(ctx, policy):
    base = {"ref_doctype": "SlaTicket", "target": 1, "done_states": "Closed"}
    errors = (ApplicationError, HTTPException)
    with pytest.raises(errors):
        await ctx.new_doc("ServiceLevel", {**base, "title": "bad start", "start_field": "title"})
    with pytest.raises(errors):
        await ctx.new_doc("ServiceLevel", {**base, "title": "bad due", "due_field": "nope"})
    with pytest.raises(errors):
        await ctx.new_doc(
            "ServiceLevel", {"title": "never done", "ref_doctype": "SlaTicket", "target": 1}
        )
