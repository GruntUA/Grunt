"""AutoRepeat - schedule arithmetic, rule validation and the daily copy job."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from grunt.tasks.auto_repeat import first_date, next_date

# ── Schedule arithmetic ──────────────────────────────────────────────────


def test_monthly_keeps_anchor_day_across_short_months():
    d = date(2026, 1, 31)
    d = next_date(d, "Monthly", 31, False)
    assert d == date(2026, 2, 28)
    d = next_date(d, "Monthly", 31, False)
    assert d == date(2026, 3, 31)


def test_last_day_and_longer_periods():
    assert next_date(date(2026, 1, 31), "Monthly", None, True) == date(2026, 2, 28)
    assert next_date(date(2026, 11, 15), "Quarterly", 15, False) == date(2027, 2, 15)
    assert next_date(date(2026, 3, 10), "Half-yearly", 10, False) == date(2026, 9, 10)
    assert next_date(date(2024, 2, 29), "Yearly", 29, False) == date(2025, 2, 28)
    assert next_date(date(2026, 1, 1), "Weekly", None, False) == date(2026, 1, 8)
    assert next_date(date(2026, 12, 31), "Daily", None, False) == date(2027, 1, 1)


def test_first_date():
    today = date(2026, 10, 8)
    # Start in the past -> first occurrence not before today.
    assert first_date(date(2026, 1, 5), "Monthly", None, False, today) == date(2026, 11, 5)
    # Day of month already passed in the start month -> next month.
    assert first_date(date(2026, 10, 8), "Monthly", 1, False, today) == date(2026, 11, 1)
    assert first_date(date(2026, 10, 8), "Monthly", 20, False, today) == date(2026, 10, 20)
    assert first_date(date(2026, 10, 8), "Daily", None, False, today) == today
    assert first_date(date(2026, 12, 1), "Weekly", None, False, today) == date(2026, 12, 1)


# ── Rules and the job ────────────────────────────────────────────────────

ITEM = {
    "name": "RepeatItem",
    "label": "Repeat Item",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {"fieldname": "posting_date", "label": "Posting date", "fieldtype": "Date"},
        {"fieldname": "auto_repeat", "label": "Auto repeat", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Reader", "read": True},
    ],
}

OWNER = "owner@grunt.example.com"


@pytest.fixture
async def template(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ITEM, "__is_new": True})
    doc = await ctx.new_doc("RepeatItem", {"title": "Rent", "posting_date": "2026-01-01"})
    await ctx.db._session().commit()
    return doc


@pytest.fixture
def owner_roles(monkeypatch):
    """Make the job resolve the rule owner to a user with these roles."""
    from grunt.tasks import auto_repeat
    from tests.support import make_user

    roles = ["System Manager"]

    async def fake_owner(email):
        return make_user(email, roles=roles)

    monkeypatch.setattr(auto_repeat, "_owner", fake_owner)
    return roles


async def _rule(ctx, template, **values):
    return await ctx.new_doc(
        "AutoRepeat",
        {
            "reference_doctype": "RepeatItem",
            "reference_document": template["name"],
            "frequency": "Monthly",
            "start_date": date.today().isoformat(),
            "notify": False,
            **values,
        },
    )


async def _backdate(ctx, name, next_on):
    await ctx.db.set_value("AutoRepeat", name, {"next_schedule_date": next_on, "owner": OWNER})
    await ctx.db._session().commit()


async def _copies(ctx):
    rows = await ctx.db.get_all(
        "RepeatItem", fields=["name", "title", "posting_date", "auto_repeat"], limit=100
    )
    return [r for r in rows if r["title"] == "Rent" and r.get("auto_repeat")]


@pytest.mark.asyncio
async def test_new_rule_is_planned(ctx, template):
    rule = await _rule(ctx, template, start_date="2026-01-05")
    assert rule["status"] == "Active"
    planned = date.fromisoformat(str(rule["next_schedule_date"])[:10])
    assert planned >= date.today()
    assert planned.day == min(5, planned.day)  # anchored on the 5th (or month end)


@pytest.mark.asyncio
async def test_rule_validation(ctx, template):
    from fastapi import HTTPException

    from grunt.errors import ApplicationError

    errors = (ApplicationError, HTTPException)
    with pytest.raises(errors):
        await _rule(ctx, template, date_field="title")  # not a date field
    with pytest.raises(errors):
        await _rule(ctx, template, start_date="2026-05-01", end_date="2026-04-01")
    with pytest.raises(errors):
        await _rule(ctx, template, reference_document="does-not-exist")
    with pytest.raises(errors):
        await ctx.new_doc(
            "AutoRepeat",
            {
                "reference_doctype": "AutoRepeat",
                "reference_document": "x",
                "frequency": "Monthly",
                "start_date": "2026-01-01",
            },
        )


@pytest.mark.asyncio
async def test_disabled_rule(ctx, template):
    rule = await _rule(ctx, template, disabled=True)
    assert rule["status"] == "Disabled"


@pytest.mark.asyncio
async def test_job_creates_missed_copies(ctx, template, owner_roles):
    from grunt.tasks.auto_repeat import process_rule

    today = date.today()
    rule = await _rule(ctx, template, frequency="Weekly", date_field="posting_date")
    await _backdate(ctx, rule["name"], today - timedelta(days=14))

    created = await process_rule(rule["name"], today)
    assert created == 3  # -14, -7, today

    copies = await _copies(ctx)
    assert len(copies) == 3
    assert {str(c["posting_date"])[:10] for c in copies} == {
        (today - timedelta(days=n)).isoformat() for n in (14, 7, 0)
    }
    assert all(c["auto_repeat"] == rule["name"] for c in copies)

    rule = await ctx.get_doc("AutoRepeat", rule["name"])
    assert rule["created_count"] == 3
    assert str(rule["next_schedule_date"])[:10] == (today + timedelta(days=7)).isoformat()
    assert rule["status"] == "Active"
    assert rule["last_document"] in {c["name"] for c in copies}
    assert not rule.get("last_error")

    # Nothing more is due today.
    assert await process_rule(rule["name"], today) == 0


@pytest.mark.asyncio
async def test_job_completes_at_end_date(ctx, template, owner_roles):
    from grunt.tasks.auto_repeat import process_rule

    today = date.today()
    rule = await _rule(
        ctx, template, frequency="Daily", start_date=(today - timedelta(days=1)).isoformat()
    )
    await ctx.db.set_value("AutoRepeat", rule["name"], "end_date", today)
    await _backdate(ctx, rule["name"], today - timedelta(days=1))

    assert await process_rule(rule["name"], today) == 2
    rule = await ctx.get_doc("AutoRepeat", rule["name"])
    assert rule["status"] == "Completed"


@pytest.mark.asyncio
async def test_job_records_failure_without_advancing(ctx, template, owner_roles):
    from grunt.tasks.auto_repeat import process_rule

    owner_roles[:] = ["Reader"]  # may read the template but not create copies
    today = date.today()
    rule = await _rule(ctx, template, frequency="Daily")
    await _backdate(ctx, rule["name"], today)

    assert await process_rule(rule["name"], today) == 0
    assert await _copies(ctx) == []
    rule = await ctx.get_doc("AutoRepeat", rule["name"])
    assert rule["last_error"]
    assert str(rule["next_schedule_date"])[:10] == today.isoformat()
    assert rule["status"] == "Active"


@pytest.mark.asyncio
async def test_repeat_action_creates_rule(ctx, template):
    from grunt.actions.builtin import auto_repeat

    res = await auto_repeat(
        {"doctype": "RepeatItem", "name": template["name"]},
        args={"frequency": "Weekly", "start_date": date.today().isoformat()},
    )
    assert "AR-" in res["message"]
    rules = await ctx.db.get_all(
        "AutoRepeat", filters={"reference_document": template["name"]}, fields=["frequency"]
    )
    assert [r["frequency"] for r in rules] == ["Weekly"]
