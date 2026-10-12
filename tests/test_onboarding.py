"""Module onboarding: steps that complete by the facts they ask for, manual
marks and skips, site vs per-user progress, roles, hiding, stable step ids."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from tests.support import make_user

pytestmark = pytest.mark.asyncio

ITEM = {
    "name": "OnbItem",
    "label": "Onb Item",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [{"role": "All", "read": True, "create": True, "write": True}],
}
SETTINGS = {
    "name": "OnbSettings",
    "label": "Onb Settings",
    "module": "core",
    "is_singleton": True,
    "fields": [
        {"fieldname": "api_key", "label": "API key", "fieldtype": "Data"},
        {"fieldname": "mode", "label": "Mode", "fieldtype": "Data"},
    ],
    "permissions": [{"role": "System Manager", "read": True, "write": True, "create": True}],
}
STEPS = [
    {"title": "Add an item", "action": "Create Entry", "reference_doctype": "OnbItem"},
    {
        "title": "Set the key",
        "action": "Update Settings",
        "reference_doctype": "OnbSettings",
        "field": "api_key",
    },
    {
        "title": "Pick live mode",
        "action": "Update Settings",
        "reference_doctype": "OnbSettings",
        "field": "mode",
        "value_to_validate": "live",
    },
    {"title": "Read the docs", "action": "Read Docs", "route": "https://example.com/docs"},
]
ANN, BEN = "ann@example.com", "ben@example.com"


@pytest.fixture
async def setup(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ITEM, "__is_new": True})
    await save_doctype(doctype_data={**SETTINGS, "__is_new": True})
    await ctx.new_doc("OnbSettings", {"name": "OnbSettings"})
    await ctx.new_doc(
        "ModuleOnboarding", {"name": "Setup", "title": "Set up", "roles": "Clerk", "steps": STEPS}
    )
    await ctx.db._session().commit()


async def _as(db_session, engine, email, fn, roles=("Clerk",)):
    import grunt

    async with grunt.context(db_session, engine, make_user(email, roles=list(roles))):
        out = await fn()
    await db_session.commit()
    return out


def _statuses(o):
    return {s["step_id"]: s["status"] for s in o["steps"]}


async def _one(db_session, engine, email=ANN, roles=("Clerk",)):
    from grunt.site.onboarding import get_onboardings

    found = await _as(db_session, engine, email, get_onboardings, roles)
    return found[0] if found else None


async def test_step_ids_are_set_and_unique(ctx, setup):
    doc = await ctx.get_doc("ModuleOnboarding", "Setup")
    assert [s["step_id"] for s in doc["steps"]] == [
        "add-an-item",
        "set-the-key",
        "pick-live-mode",
        "read-the-docs",
    ]
    twin = await ctx.new_doc(
        "ModuleOnboarding",
        {
            "name": "Twin",
            "title": "T",
            "steps": [{"title": "A", "action": "Read Docs", "route": "x"} for _ in range(2)],
        },
    )
    assert [s["step_id"] for s in twin["steps"]] == ["a", "a-2"]


async def test_auto_steps_follow_the_facts(ctx, setup, db_session, engine):
    o = await _one(db_session, engine)
    assert o is not None
    assert o["done"] == 0 and o["total"] == 4
    assert o["steps"][0]["target"] == {"type": "DocType", "name": "OnbItem", "id": "new"}

    await ctx.new_doc("OnbItem", {"title": "x"})
    await ctx.save_doc("OnbSettings", "OnbSettings", {"api_key": "k", "mode": "test"})
    await ctx.db._session().commit()
    assert _statuses(await _one(db_session, engine)) == {
        "add-an-item": "Completed",
        "set-the-key": "Completed",
        "pick-live-mode": "Pending",  # must equal "live"
        "read-the-docs": "Pending",
    }


async def test_manual_marks_are_shared_on_a_site_checklist(ctx, setup, db_session, engine):
    from grunt.site.onboarding import mark_step

    await _as(db_session, engine, ANN, lambda: mark_step("Setup", "read-the-docs"))
    await _as(db_session, engine, ANN, lambda: mark_step("Setup", "pick-live-mode", "Skipped"))
    seen_by_ben = _statuses(await _one(db_session, engine, BEN))
    assert seen_by_ben["read-the-docs"] == "Completed"
    assert seen_by_ben["pick-live-mode"] == "Skipped"

    await _as(db_session, engine, BEN, lambda: mark_step("Setup", "read-the-docs", "Pending"))
    assert _statuses(await _one(db_session, engine))["read-the-docs"] == "Pending"


async def test_user_checklist_counts_own_records(ctx, setup, db_session, engine):
    from grunt.site.onboarding import mark_step

    await ctx.save_doc("ModuleOnboarding", "Setup", {"progress_scope": "User"})
    await ctx.db._session().commit()
    await _as(db_session, engine, ANN, lambda: ctx.new_doc("OnbItem", {"title": "mine"}))
    await _as(db_session, engine, ANN, lambda: mark_step("Setup", "read-the-docs"))

    assert _statuses(await _one(db_session, engine, ANN))["add-an-item"] == "Completed"
    ben = _statuses(await _one(db_session, engine, BEN))
    assert ben["add-an-item"] == "Pending"
    assert ben["read-the-docs"] == "Pending"


async def test_roles_and_hiding(ctx, setup, db_session, engine):
    from grunt.site.onboarding import hide_onboarding, mark_step

    assert await _one(db_session, engine, BEN, roles=("Other",)) is None
    with pytest.raises((ApplicationError, HTTPException)):
        await _as(db_session, engine, BEN, lambda: mark_step("Setup", "read-the-docs"), ("Other",))

    await _as(db_session, engine, ANN, lambda: hide_onboarding("Setup"))
    assert await _one(db_session, engine, ANN) is None
    assert await _one(db_session, engine, BEN) is not None  # hidden only for Ann
