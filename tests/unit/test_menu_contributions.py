"""Apps that extend another app's menu (``"extends"`` AppMenu fixtures).

The contributed rows carry ``source_app``: the base app's own sync leaves them
alone, and ``order_menu`` places them by their ``after``/``before`` anchors.
"""

import pytest

from grunt.site.doctypes.AppMenu.app_menu import order_menu
from grunt.startup.workspaces import _apply_workspace_fixture

BASE = [
    {
        "name": "inv",
        "label": "Inventory",
        "items": [
            {"section": "Assets", "label": "Assets", "link_to": "Asset"},
            {"section": "Agents", "label": "Agents", "link_to": "Agent"},
            {"section": "Settings", "label": "Inventory settings", "link_to": "InvSettings"},
        ],
    }
]

CONTRIBUTION = [
    {
        "extends": "inv",
        "sections": [{"section": "Crystal", "icon": "landmark", "after": "Agents"}],
        "items": [
            {"section": "Crystal", "label": "Cards", "link_to": "CfCard"},
            {"section": "Crystal", "label": "Items", "link_to": "CfItem"},
            {"section": "Settings", "label": "Crystal settings", "link_to": "CfSettings"},
        ],
    }
]


async def _rows(ctx, doctype: str, **filters) -> list[dict]:
    return await ctx.get_list(
        doctype,
        filters={"parent_name": "inv", **filters},
        fields=["label", "section", "source_app", "anchor_after", "idx"],
        order_by="idx",
        order="asc",
    )


@pytest.mark.asyncio
async def test_contribution_survives_base_resync(ctx):
    assert await _apply_workspace_fixture(BASE, "inv", {}) is True
    # A contribution is not the app's own menu - auto-seeding must still be decided by it.
    assert await _apply_workspace_fixture(CONTRIBUTION, "crystal", {}) is False

    changed = [{**BASE[0], "items": [*BASE[0]["items"], {"section": "Assets", "label": "Ports"}]}]
    await _apply_workspace_fixture(changed, "inv", {})

    items = await _rows(ctx, "WorkspaceSidebarItem")
    assert [i["label"] for i in items if i["source_app"] == "crystal"] == [
        "Cards",
        "Items",
        "Crystal settings",
    ]
    assert "Ports" in [i["label"] for i in items if not i["source_app"]]
    sections = await _rows(ctx, "WorkspaceSection")
    assert [(s["section"], s["anchor_after"]) for s in sections] == [("Crystal", "Agents")]


@pytest.mark.asyncio
async def test_contribution_resync_replaces_only_its_rows(ctx):
    await _apply_workspace_fixture(BASE, "inv", {})
    await _apply_workspace_fixture(CONTRIBUTION, "crystal", {})
    await _apply_workspace_fixture(
        [{"extends": "inv", "items": [{"section": "Crystal", "label": "Only"}]}], "crystal", {}
    )

    items = await _rows(ctx, "WorkspaceSidebarItem", source_app="crystal")
    assert [i["label"] for i in items] == ["Only"]
    assert await ctx.get_list("WorkspaceSection", filters={"source_app": "crystal"}) == []
    assert len(await _rows(ctx, "WorkspaceSidebarItem", source_app__is="not set")) == 3


@pytest.mark.asyncio
async def test_contribution_to_missing_menu_is_skipped(ctx):
    assert await _apply_workspace_fixture(CONTRIBUTION, "crystal", {}) is False
    assert await ctx.get_list("WorkspaceSidebarItem", filters={"source_app": "crystal"}) == []


@pytest.mark.asyncio
async def test_menu_api_orders_contributed_rows(ctx):
    from grunt.api.v1.workspace import _workspace_to_dict

    await _apply_workspace_fixture(BASE, "inv", {})
    await _apply_workspace_fixture(CONTRIBUTION, "crystal", {})

    data = await _workspace_to_dict(await ctx.get_doc("AppMenu", "inv"))

    assert [i["label"] for i in data["items"]] == [
        "Assets",
        "Agents",
        "Cards",
        "Items",
        "Inventory settings",
        "Crystal settings",
    ]
    assert [i["sequence"] for i in data["items"]] == list(range(6))
    assert [s["section"] for s in data["sections"]] == ["Assets", "Agents", "Crystal", "Settings"]


def _item(label, section, idx, source_app="", after="", before=""):
    return {
        "label": label,
        "link_to": label,
        "section": section,
        "idx": idx,
        "source_app": source_app,
        "anchor_after": after,
        "anchor_before": before,
    }


def _labels(rows):
    return [r["label"] for r in rows]


def test_order_item_anchors():
    items = [
        _item("A", "S", 0),
        _item("B", "S", 1),
        _item("C", "S", 2),
        _item("x", "S", 0, "ext", after="A"),
        _item("y", "S", 1, "ext", before="A"),
    ]
    assert _labels(order_menu(items, [])) == ["y", "A", "x", "B", "C"]


def test_order_new_section_before_anchor_and_fallback_to_end():
    items = [
        _item("A", "S1", 0),
        _item("B", "S2", 1),
        _item("n", "New", 0, "ext"),
        _item("z", "Lost", 1, "ext", after="Nope"),
    ]
    sections = [{"section": "New", "anchor_before": "S2", "source_app": "ext"}]
    assert _labels(order_menu(items, sections)) == ["A", "n", "B", "z"]


def test_order_apps_are_placed_in_name_order():
    items = [
        _item("A", "S", 0),
        _item("b1", "S", 0, "beta"),
        _item("a1", "S", 0, "alpha"),
    ]
    assert _labels(order_menu(items, [])) == ["A", "a1", "b1"]


@pytest.mark.asyncio
async def test_uninstall_removes_contributed_rows(ctx):
    from grunt.cli.app import _delete_workspace_and_registration

    await _apply_workspace_fixture(BASE, "inv", {})
    await _apply_workspace_fixture(CONTRIBUTION, "crystal", {})

    await _delete_workspace_and_registration(
        name="crystal", has_workspace=False, has_installed_row=False
    )

    assert await ctx.get_list("WorkspaceSidebarItem", filters={"source_app": "crystal"}) == []
    assert await ctx.get_list("WorkspaceSection", filters={"source_app": "crystal"}) == []
    assert len(await _rows(ctx, "WorkspaceSidebarItem")) == 3
