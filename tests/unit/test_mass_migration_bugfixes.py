"""Regression tests for the Phase-1 mass-migration bug fixes (see ADR 004 /
docs/adr/004-api-v2-primitives.md): dead `if not doc:` checks after `get_doc`
(which raises before it can return falsy) and manual controller instantiation
after a dict-returning `get_doc` call.
"""

from __future__ import annotations

import pytest

import grunt
from grunt.errors import APIError
from tests.support import make_user


@pytest.mark.asyncio
async def test_get_doc_instance_resolves_real_controller_method(ctx):
    """Regression: grunt/tasks/doc_method.py's _run_doc_method used to fetch the
    document via grunt.get_doc(doctype_str, id) (a plain dict) and then do
    getattr(doc, method, None) — always None, since dicts don't expose
    arbitrary attributes, so enqueue_doc_method *always* raised AttributeError
    regardless of whether the method existed. Swapped to get_doc_instance(),
    which returns a bound controller instance with real methods."""
    from grunt.auth.doctypes.User.user import User

    user = await User.objects.create(
        email="doc-method-bugfix@grunt.example.com",
        password="secret",
        first_name="Doc",
        last_name="Method",
        is_active=True,
    )

    doc = await grunt.get_doc_instance("User", user.name)
    handler = getattr(doc, "check_password", None)
    assert handler is not None
    assert callable(handler)
    assert await handler("secret") is True


@pytest.mark.asyncio
async def test_workspace_get_workspace_returns_saved_data(ctx):
    """workspace.py's get_workspace()/_get_ws_controller() now go through
    typed grunt.get_doc(AppMenu, name) — this exercises the actual dead-code
    path that used to be `if not doc_data: grunt.throw(...)` (unreachable)."""
    from grunt.api.v1.workspace import get_workspace

    admin = make_user("ws-admin@grunt.example.com", is_superadmin=True)
    async with ctx.context(ctx.db._session(), ctx._require_engine(), admin):
        created = await ctx.new_doc("AppMenu", {"label": "Test Workspace", "app": "grunt"})
        await ctx.db._session().commit()

        result = await get_workspace(created["name"])
        assert result["label"] == "Test Workspace"


@pytest.mark.asyncio
async def test_workspace_get_workspace_404_for_missing(ctx):
    from fastapi import HTTPException

    from grunt.api.v1.workspace import get_workspace

    admin = make_user("ws-admin2@grunt.example.com", is_superadmin=True)
    async with ctx.context(ctx.db._session(), ctx._require_engine(), admin):
        with pytest.raises(HTTPException) as excinfo:
            await get_workspace("does-not-exist")
        assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_workspace_save_requires_system_manager(ctx):
    from grunt.api.v1.workspace import save_workspace

    regular = make_user("ws-regular@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx._require_engine(), regular):
        with pytest.raises(APIError) as excinfo:
            await save_workspace({"label": "Should Not Save", "app": "grunt"})
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_assignment_preview_rule_resolves_typed_doc(ctx):
    """assignment/service.py's preview_rule() used to do
    grunt.get_doc("AssignmentRule", id) + AssignmentRule(...) manually —
    now a single typed grunt.get_doc(AssignmentRule, id) call."""
    from grunt.assignment.service import AssignmentService

    admin = make_user("assign-admin@grunt.example.com", is_superadmin=True)
    async with ctx.context(ctx.db._session(), ctx._require_engine(), admin):
        rule_doc = await ctx.new_doc(
            "AssignmentRule",
            {
                "doctype_target": "User",
                "enabled": True,
                "assign_to_user": "someone@grunt.example.com",
            },
        )
        await ctx.db._session().commit()

        result = await AssignmentService().preview_rule(rule_doc["name"], {"name": "x"})
        assert result["rule_id"] == rule_doc["name"]


@pytest.mark.asyncio
async def test_workspace_list_workspaces_with_sidebar_items(ctx):
    """list_workspaces() batch-preloads DocType metadata (doctype_registry.list_all())
    before resolving sidebar items, instead of one lazy-load per item — this just
    checks the resulting data is still correct after that change."""
    from grunt.api.v1.workspace import list_workspaces

    admin = make_user("ws-perf-admin@grunt.example.com", is_superadmin=True)
    async with ctx.context(ctx.db._session(), ctx._require_engine(), admin):
        await ctx.new_doc(
            "AppMenu",
            {
                "label": "Perf Test WS",
                "app": "grunt",
                "sidebar_items": [
                    {"type": "DocType", "link_to": "User", "label": "Users", "idx": 0},
                    {"type": "DocType", "link_to": "DocType", "label": "DocTypes", "idx": 1},
                ],
            },
        )
        await ctx.db._session().commit()

        result = await list_workspaces()
        ws = next(w for w in result if w["label"] == "Perf Test WS")
        assert [i["link_to"] for i in ws["items"]] == ["User", "DocType"]
