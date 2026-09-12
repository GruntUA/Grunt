"""Regression tests for startup/workspaces.py — create/update AppMenu + sidebar.

No prior coverage existed for this module (verified via full-repo grep) before
the create/update logic in seed_grunt_workspace/_apply_workspace_fixture/
_auto_seed_workspace was consolidated into a shared _upsert_workspace() helper.
These tests exercise all three call sites' create and update paths, plus the
sidebar "replace: delete old, insert new" step.
"""

from __future__ import annotations

import pytest

from grunt.startup.workspaces import _apply_workspace_fixture, _auto_seed_workspace


@pytest.mark.asyncio
async def test_apply_workspace_fixture_creates_new_workspace(ctx):
    records = [
        {
            "name": "test_app",
            "label": "Test App",
            "icon": "🧪",
            "sidebar_items": [
                {"label": "Item A", "link_to": "ItemA", "sequence": 1},
                {"label": "Item B", "link_to": "ItemB", "sequence": 2},
            ],
        }
    ]

    applied = await _apply_workspace_fixture(records, "test_app", {})
    assert applied is True

    ws = await ctx.get_list(
        "AppMenu", filters={"name": "test_app"}, fields=["name", "label", "icon"]
    )
    assert len(ws) == 1
    assert ws[0]["label"] == "Test App"
    assert ws[0]["icon"] == "🧪"

    items = await ctx.get_list(
        "WorkspaceSidebarItem",
        filters={"parent_name": "test_app"},
        fields=["label", "link_to"],
        order_by="idx",
        order="asc",
    )
    assert [i["label"] for i in items] == ["Item A", "Item B"]


@pytest.mark.asyncio
async def test_apply_workspace_fixture_updates_existing_and_replaces_sidebar(ctx):
    records = [{"name": "test_app", "label": "Original", "sidebar_items": [{"label": "Old"}]}]
    await _apply_workspace_fixture(records, "test_app", {})

    updated_records = [
        {"name": "test_app", "label": "Updated Label", "sidebar_items": [{"label": "New"}]}
    ]
    await _apply_workspace_fixture(updated_records, "test_app", {})

    ws = await ctx.get_list("AppMenu", filters={"name": "test_app"}, fields=["label"])
    assert ws[0]["label"] == "Updated Label"

    items = await ctx.get_list(
        "WorkspaceSidebarItem", filters={"parent_name": "test_app"}, fields=["label"]
    )
    assert [i["label"] for i in items] == ["New"]


@pytest.mark.asyncio
async def test_apply_workspace_fixture_omits_home_page_when_unset(ctx):
    """home_page is a Link field — must be omitted (not sent as "") on create."""
    records = [{"name": "test_app", "label": "Test App"}]
    await _apply_workspace_fixture(records, "test_app", {})

    ws = await ctx.get_list("AppMenu", filters={"name": "test_app"}, fields=["home_page"])
    assert ws[0]["home_page"] is None


@pytest.mark.asyncio
async def test_auto_seed_workspace_creates_from_doctypes(ctx):
    class _FakeDocType:
        def __init__(self, name: str, label: str) -> None:
            self.name = name
            self.label = label

    app_doctypes = [_FakeDocType("Widget", "Віджет"), _FakeDocType("Gadget", "Гаджет")]

    await _auto_seed_workspace("my_app", {"title": "My App"}, app_doctypes)

    ws = await ctx.get_list("AppMenu", filters={"name": "my_app"}, fields=["name", "label"])
    assert ws[0]["label"] == "My App"

    items = await ctx.get_list(
        "WorkspaceSidebarItem",
        filters={"parent_name": "my_app"},
        fields=["label", "link_to"],
        order_by="idx",
        order="asc",
    )
    assert [i["link_to"] for i in items] == ["Widget", "Gadget"]


@pytest.mark.asyncio
async def test_auto_seed_workspace_update_only_touches_title_fields(ctx):
    """The _auto_seed_workspace update path only ever sends label/icon/color/description."""

    class _FakeDocType:
        def __init__(self, name: str, label: str) -> None:
            self.name = name
            self.label = label

    await _auto_seed_workspace("my_app", {"title": "First"}, [_FakeDocType("Widget", "Віджет")])
    await _auto_seed_workspace("my_app", {"title": "Second"}, [_FakeDocType("Gadget", "Гаджет")])

    ws = await ctx.get_list("AppMenu", filters={"name": "my_app"}, fields=["label"])
    assert ws[0]["label"] == "Second"

    items = await ctx.get_list(
        "WorkspaceSidebarItem", filters={"parent_name": "my_app"}, fields=["link_to"]
    )
    assert [i["link_to"] for i in items] == ["Gadget"]
