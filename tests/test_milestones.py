"""Milestones: time spent in each value of a tracked field."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from grunt.activity import milestones
from grunt.errors import ApplicationError
from tests.support import make_user

CASE = {
    "name": "MsCase",
    "label": "MS Case",
    "module": "core",
    "status_field": "status",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "New\nWorking\nDone",
            "default": "New",
        },
        {"fieldname": "stage", "label": "Stage", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Clerk", "read": True, "match": "owner == user"},
    ],
}

ERRORS = (ApplicationError, HTTPException)


@pytest.fixture
async def cases(ctx):
    from grunt.api.v1.meta import save_doctype

    milestones.invalidate()
    await save_doctype(doctype_data={**CASE, "__is_new": True})
    await ctx.db._session().commit()
    yield
    milestones.invalidate()


async def _rows(ctx, name):
    return await ctx.db.get_all(
        "Milestone",
        filters={"ref_doctype": "MsCase", "ref_name": name},
        order_by="entered_at",
        order="asc",
    )


@pytest.mark.asyncio
async def test_status_changes_open_and_close_milestones(ctx, cases):
    tracker = await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase"})
    assert tracker["track_field"] == "status"  # the DocType's status field by default

    case = await ctx.new_doc("MsCase", {"title": "A"})
    await ctx.save_doc("MsCase", case["name"], {"title": "renamed"})  # no status change
    await ctx.save_doc("MsCase", case["name"], {"status": "Working"})
    await ctx.save_doc("MsCase", case["name"], {"status": "Done"})

    rows = await _rows(ctx, case["name"])
    assert [(r["value"], r["previous_value"]) for r in rows] == [
        ("New", None),
        ("Working", "New"),
        ("Done", "Working"),
    ]
    assert rows[0]["left_at"] and rows[0]["duration_hours"] is not None
    assert rows[-1]["left_at"] is None and rows[-1]["duration_hours"] is None
    assert rows[1]["entered_by"] == "system@grunt.local"


@pytest.mark.asyncio
async def test_durations_and_aggregate(ctx, cases):
    await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase"})
    case = await ctx.new_doc("MsCase", {"title": "B"})
    start = datetime.now(UTC) - timedelta(hours=5)
    [first] = await _rows(ctx, case["name"])
    await ctx.db.set_value("Milestone", first["name"], "entered_at", start)

    await milestones.record(
        "MsCase", {**case, "status": "Working"}, "status", at=start + timedelta(hours=3)
    )
    rows = await _rows(ctx, case["name"])
    assert rows[0]["duration_hours"] == 3.0

    stats = await ctx.aggregate(
        "Milestone",
        filters={"ref_doctype": "MsCase", "left_at__isnull": False},
        group_by="value",
        aggregations={"avg": "avg(duration_hours)"},
    )
    assert stats == [{"value": "New", "avg": 3.0}]


@pytest.mark.asyncio
async def test_seed_existing_documents(ctx, cases):
    a = await ctx.new_doc("MsCase", {"title": "Old A", "status": "Working"})
    b = await ctx.new_doc("MsCase", {"title": "Old B"})
    assert await _rows(ctx, a["name"]) == []

    await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase"})
    [ra] = await _rows(ctx, a["name"])
    [rb] = await _rows(ctx, b["name"])
    assert (ra["value"], rb["value"]) == ("Working", "New")
    assert ra["approximate"] and rb["approximate"]


@pytest.mark.asyncio
async def test_other_field_disable_and_validation(ctx, cases):
    tracker = await ctx.new_doc(
        "MilestoneTracker", {"ref_doctype": "MsCase", "track_field": "stage"}
    )
    case = await ctx.new_doc("MsCase", {"title": "C", "stage": "intake"})
    await ctx.save_doc("MsCase", case["name"], {"stage": "review"})
    assert [r["value"] for r in await _rows(ctx, case["name"])] == ["intake", "review"]

    await ctx.save_doc("MilestoneTracker", tracker["name"], {"disabled": True})
    await ctx.save_doc("MsCase", case["name"], {"stage": "closed"})
    assert len(await _rows(ctx, case["name"])) == 2

    with pytest.raises(ERRORS):
        await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase", "track_field": "nope"})
    await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase"})
    with pytest.raises(ERRORS):  # status already tracked
        await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase", "track_field": "status"})


@pytest.mark.asyncio
async def test_delete_and_permissions(ctx, cases, db_session, engine):
    import grunt
    from grunt.document.base import Document

    await ctx.new_doc("MilestoneTracker", {"ref_doctype": "MsCase"})
    clerk = "clerk@example.com"
    async with grunt.context(db_session, engine, make_user(clerk, roles=["System Manager"])):
        own = await grunt.new_doc("MsCase", {"title": "Own"})
    other = await ctx.new_doc("MsCase", {"title": "Other"})
    await db_session.commit()

    async with grunt.context(db_session, engine, make_user(clerk, roles=["Clerk"])):
        visible = await grunt.get_list("Milestone", filters={"ref_doctype": "MsCase"}, limit=50)
        assert {r["ref_name"] for r in visible} == {own["name"]}
        sidebar = await Document.get_sidebar(doctype="MsCase", doc_id=own["name"])
        assert [m["value"] for m in sidebar["milestones"]] == ["New"]

    await ctx.delete_doc("MsCase", other["name"])
    assert await _rows(ctx, other["name"]) == []
