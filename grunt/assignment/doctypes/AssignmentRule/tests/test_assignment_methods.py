"""Assignment rules choose (FRAPPE_GAP #9): round robin, load balancing, a
field, everyone; priority, days of the week, the due date; close / unassign
conditions; a rule also assigns on save, once."""

import json

import pytest

from grunt.api.v1.meta import save_doctype
from grunt.assignment.service import DAYS
from grunt.utils.dates import local_today

USERS = ["ann@grunt.example.com", "bob@grunt.example.com", "cid@grunt.example.com"]


@pytest.fixture
async def setup(ctx):
    await save_doctype(
        doctype_data={
            "name": "Ticket",
            "label": "Ticket",
            "module": "crm",
            "__is_new": True,
            "fields": [
                {"fieldname": "subject", "label": "Subject", "fieldtype": "Data"},
                {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
                {"fieldname": "agent", "label": "Agent", "fieldtype": "Link", "options": "User"},
                {"fieldname": "due", "label": "Due", "fieldtype": "Date"},
            ],
        }
    )
    for email in USERS:
        await ctx.new_doc("User", {"email": email, "first_name": email[:3], "last_name": "Test"})
    await ctx.db._session().commit()


async def _rule(ctx, **values) -> dict:
    rule = await ctx.new_doc(
        "AssignmentRule", {"doctype_target": "Ticket", "enabled": True, **values}
    )
    await ctx.db._session().commit()
    return rule


async def _ticket(ctx, **values) -> str:
    doc = await ctx.new_doc("Ticket", {"subject": "x", "status": "Open", **values})
    await ctx.db._session().commit()
    return doc["name"]


async def _assignees(ctx, ticket: str, status: str = "Open") -> list[str]:
    rows = await ctx.db.get_all(
        "ToDo",
        filters={"reference_doctype": "Ticket", "reference_id": ticket, "status": status},
        fields=["assigned_to"],
        limit=None,
    )
    return sorted(r["assigned_to"] for r in rows)


def _users(*pairs) -> list[dict]:
    return [{"user": u, "weight": w} for u, w in pairs]


@pytest.mark.asyncio
async def test_round_robin_with_weights(ctx, setup):
    a, b, c = USERS
    await _rule(ctx, rule="Round Robin", users=_users((a, 1), (b, 2), (c, 1)))
    got = [(await _assignees(ctx, await _ticket(ctx)))[0] for _ in range(5)]
    assert got == [a, b, b, c, a]


@pytest.mark.asyncio
async def test_load_balancing_picks_the_least_busy(ctx, setup):
    a, b, c = USERS
    for user, n in ((a, 2), (b, 1)):
        for _ in range(n):
            await ctx.new_doc(
                "ToDo", {"description": "busy", "assigned_to": user, "status": "Open"}
            )
    await ctx.db._session().commit()
    await _rule(ctx, rule="Load Balancing", users=_users((a, 1), (b, 1), (c, 1)))
    assert await _assignees(ctx, await _ticket(ctx)) == [c]
    # c has one now, b one - b comes first in the list.
    assert await _assignees(ctx, await _ticket(ctx)) == [b]


@pytest.mark.asyncio
async def test_based_on_field_and_everyone(ctx, setup):
    a, b, c = USERS
    await _rule(
        ctx,
        rule="Based on Field",
        field="agent",
        priority=2,
        filters=json.dumps({"status": "Open"}),
    )
    await _rule(
        ctx, rule="Everyone", users=_users((a, 1), (c, 1)), filters=json.dumps({"status": "New"})
    )
    assert await _assignees(ctx, await _ticket(ctx, agent=b)) == [b]
    assert await _assignees(ctx, await _ticket(ctx, status="New")) == [a, c]


@pytest.mark.asyncio
async def test_first_rule_by_priority_wins(ctx, setup):
    a, b, _c = USERS
    await _rule(ctx, rule="Everyone", users=_users((a, 1)), priority=1)
    await _rule(ctx, rule="Everyone", users=_users((b, 1)), priority=5)
    assert await _assignees(ctx, await _ticket(ctx)) == [b]


@pytest.mark.asyncio
async def test_assigns_on_save_once_then_closes_or_unassigns(ctx, setup):
    a, b, c = USERS
    await _rule(
        ctx,
        rule="Round Robin",
        users=_users((a, 1), (b, 1), (c, 1)),
        filters=json.dumps({"status": "Open"}),
        close_condition=json.dumps({"status": "Answered"}),
        unassign_condition=json.dumps({"status": "Cancelled"}),
    )
    ticket = await _ticket(ctx, status="Draft")
    assert await _assignees(ctx, ticket) == []

    await ctx.save_doc("Ticket", ticket, {"status": "Open"})  # reaches the state
    await ctx.save_doc("Ticket", ticket, {"subject": "edited"})  # no second assignee
    await ctx.db._session().commit()
    assert await _assignees(ctx, ticket) == [a]

    await ctx.save_doc("Ticket", ticket, {"status": "Answered"})
    await ctx.db._session().commit()
    assert await _assignees(ctx, ticket) == []
    assert await _assignees(ctx, ticket, "Closed") == [a]

    other = await _ticket(ctx)
    await ctx.save_doc("Ticket", other, {"status": "Cancelled"})
    await ctx.db._session().commit()
    assert await _assignees(ctx, other, "Cancelled") == [b]


@pytest.mark.asyncio
async def test_days_and_due_date(ctx, setup):
    a, _b, _c = USERS
    today = DAYS[local_today().weekday()]
    other_days = [d for d in DAYS if d != today]
    await _rule(ctx, users=_users((a, 1)), days=other_days, priority=9)
    await _rule(ctx, users=_users((a, 1)), days=[today], due_date_field="due")
    ticket = await _ticket(ctx, due="2026-12-01")
    todo = await ctx.db.get_all(
        "ToDo", filters={"reference_id": ticket}, fields=["due_date"], limit=None
    )
    assert len(todo) == 1 and str(todo[0]["due_date"]) == "2026-12-01"


@pytest.mark.asyncio
async def test_preview_names_the_users_of_a_rule_read_by_class(ctx, setup):
    from grunt.assignment.doctypes.AssignmentRule.assignment_rule import test_rule

    a, b, _ = USERS
    rule = await _rule(ctx, rule="Everyone", users=_users((a, 1), (b, 1)))
    result = await test_rule(rule["name"], {"subject": "x", "status": "Open"})
    assert result["matched"] is True
    assert sorted(result["will_assign_to"]) == [a, b]
