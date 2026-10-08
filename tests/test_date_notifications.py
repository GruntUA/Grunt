"""Date-based notification rules: N days before/after a date, yearly, once a day."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.notification import date_rules

CONTRACT = {
    "name": "Contract",
    "label": "Contract",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "end_date", "label": "End", "fieldtype": "Date"},
        {"fieldname": "signed_at", "label": "Signed", "fieldtype": "Datetime"},
        {"fieldname": "birthday", "label": "Birthday", "fieldtype": "Date"},
        {"fieldname": "manager", "label": "Manager", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True}
    ],
}

MANAGER = "manager@grunt.example.com"


def test_same_day_of_year():
    assert date_rules.same_day_of_year(date(1990, 5, 17), date(2026, 5, 17))
    assert not date_rules.same_day_of_year(date(1990, 5, 17), date(2026, 5, 18))
    # Leap-day birthdays are celebrated on Feb 28 in other years.
    assert date_rules.same_day_of_year(date(2000, 2, 29), date(2026, 2, 28))
    assert not date_rules.same_day_of_year(date(2000, 2, 29), date(2028, 2, 28))


def test_target_date():
    today = date(2026, 10, 8)
    assert date_rules.target_date({"event": "days_before", "days": 30}, today) == date(2026, 11, 7)
    assert date_rules.target_date({"event": "days_after", "days": 3}, today) == date(2026, 10, 5)
    assert date_rules.target_date({"event": "days_before", "days": 0}, today) == today


@pytest.fixture
async def contracts(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**CONTRACT, "__is_new": True})
    await ctx.db._session().commit()


async def _rule(ctx, **values):
    return await ctx.new_doc(
        "NotificationRule",
        {
            "ref_doctype": "Contract",
            "recipients": "{field:manager}",
            "subject_template": "{title}",
            "message_template": "{title}",
            **values,
        },
    )


async def _subjects(ctx):
    rows = await ctx.db.get_all("Notification", filters={"user": MANAGER}, fields=["subject"])
    return sorted(r["subject"] for r in rows)


async def _contract(ctx, title, **values):
    return await ctx.new_doc("Contract", {"title": title, "manager": MANAGER, **values})


@pytest.mark.asyncio
async def test_days_before_a_date(ctx, contracts):
    today = date_rules.local_today()
    rule = await _rule(ctx, event="days_before", date_field="end_date", days=30)
    await _contract(ctx, "Due", end_date=today + timedelta(days=30))
    await _contract(ctx, "Later", end_date=today + timedelta(days=31))
    await _contract(ctx, "No date")

    assert await date_rules.run_rule(rule, today) == 1
    assert await _subjects(ctx) == ["Due"]

    # Once a day per document: a rerun sends nothing.
    assert await date_rules.run_rule(rule, today) == 0
    assert await _subjects(ctx) == ["Due"]
    # The next day another contract may be due.
    assert await date_rules.run_rule(rule, today + timedelta(days=1)) == 1
    assert await _subjects(ctx) == ["Due", "Later"]


@pytest.mark.asyncio
async def test_days_after_a_datetime_uses_the_local_day(ctx, contracts):
    today = date_rules.local_today()
    rule = await _rule(ctx, event="days_after", date_field="signed_at", days=0)
    late_evening = datetime.combine(today, time(23, 30), tzinfo=date_rules._tz())
    yesterday = datetime.combine(today - timedelta(days=1), time(23, 30), tzinfo=date_rules._tz())
    await _contract(ctx, "Tonight", signed_at=late_evening)
    await _contract(ctx, "Yesterday", signed_at=yesterday)

    assert await date_rules.run_rule(rule, today) == 1
    assert await _subjects(ctx) == ["Tonight"]


@pytest.mark.asyncio
async def test_every_year_and_condition(ctx, contracts):
    today = date_rules.local_today()
    rule = await _rule(
        ctx,
        event="days_before",
        date_field="birthday",
        days=0,
        every_year=True,
        condition="doc.get('title') != 'Muted'",
    )
    await _contract(ctx, "Birthday", birthday=today.replace(year=1990, day=min(today.day, 28)))
    await _contract(ctx, "Muted", birthday=today.replace(year=1985, day=min(today.day, 28)))
    await _contract(ctx, "Other day", birthday=(today + timedelta(days=40)).replace(year=1990))

    due_day = today.replace(day=min(today.day, 28))
    assert await date_rules.run_rule(rule, due_day) == 1
    assert await _subjects(ctx) == ["Birthday"]


@pytest.mark.asyncio
async def test_save_events_ignore_date_rules(ctx, contracts):
    """A date rule never fires on save - only the daily job runs it."""
    from grunt.notification.service import notification_service

    await _rule(ctx, event="days_before", date_field="end_date", days=0)
    doc = await _contract(ctx, "Saved", end_date=date_rules.local_today())
    sent = await notification_service.evaluate_rules(
        ctx.db._session(), "after_save", "Contract", doc, "someone@example.com"
    )
    assert sent == 0


@pytest.mark.asyncio
async def test_rule_validation(ctx, contracts):
    errors = (ApplicationError, HTTPException)
    with pytest.raises(errors):
        await _rule(ctx, event="days_before", date_field="title", days=1)
    with pytest.raises(errors):
        await _rule(ctx, event="days_after", date_field="", days=1)
    # created_at is always a valid anchor ("3 days after creation").
    ok = await _rule(ctx, event="days_after", date_field="created_at", days=3)
    assert ok["date_field"] == "created_at"
