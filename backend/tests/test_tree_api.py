"""Tests for tree filtering via GET /docs/{doctype}/tree.

Verifies that filter[field__op]=value params correctly prune the tree
to matching nodes + their ancestors.
"""

from __future__ import annotations

import pytest

TREE_DOCTYPE = {
    "name": "TreeCategory",
    "label": "Tree Category",
    "module": "core",
    "is_tree": True,
    "tree_view": {
        "parent_field": "parent_category",
        "title_field": "title",
    },
    "fields": [
        {
            "fieldname": "title",
            "label": "Title",
            "fieldtype": "Text",
            "required": True,
            "in_list_view": True,
            "in_filter": True,
        },
        {
            "fieldname": "parent_category",
            "label": "Parent Category",
            "fieldtype": "Link",
            "options": "TreeCategory",
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Active\nInactive",
            "default": "Active",
            "in_filter": True,
        },
    ],
    "search_fields": ["title"],
}


@pytest.fixture
async def tree_doctype(ctx):
    """Create TreeCategory DocType and a small tree structure."""
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**TREE_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()

    # Tree structure:
    #  Root-A (Active)
    #    Child-A1 (Active)
    #    Child-A2 (Inactive)
    #  Root-B (Inactive)
    #    Child-B1 (Active)

    root_a = await ctx.new_doc("TreeCategory", {"title": "Root-A", "status": "Active"})
    root_b = await ctx.new_doc("TreeCategory", {"title": "Root-B", "status": "Inactive"})
    child_a1 = await ctx.new_doc(
        "TreeCategory",
        {"title": "Child-A1", "status": "Active", "parent_category": root_a["name"]},
    )
    child_a2 = await ctx.new_doc(
        "TreeCategory",
        {"title": "Child-A2", "status": "Inactive", "parent_category": root_a["name"]},
    )
    child_b1 = await ctx.new_doc(
        "TreeCategory",
        {"title": "Child-B1", "status": "Active", "parent_category": root_b["name"]},
    )
    await ctx.db._session().commit()

    return {
        "root_a": root_a,
        "root_b": root_b,
        "child_a1": child_a1,
        "child_a2": child_a2,
        "child_b1": child_b1,
    }


def _collect_titles(nodes: list) -> set:
    """Recursively collect all title values from a nested tree."""
    titles: set = set()
    for node in nodes:
        titles.add(node["title"])
        titles.update(_collect_titles(node.get("children") or []))
    return titles


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tree_filter_active_nodes(ctx, tree_doctype):
    """filter[status__eq]=Active returns Active nodes + their ancestors."""
    from grunt.core.document.tree import tree_service

    session = ctx.db._session()
    nodes = await tree_service.get_tree(
        session,
        "TreeCategory",
        filters={"status__eq": "Active"},
    )

    titles = _collect_titles(nodes)

    # Active leaf nodes should be present
    assert "Child-A1" in titles  # Active
    assert "Child-B1" in titles  # Active

    # Root-A must be present as ancestor of Child-A1
    assert "Root-A" in titles

    # Root-B must be present as ancestor of Child-B1
    assert "Root-B" in titles

    # Inactive nodes with no active descendants must be absent
    assert "Child-A2" not in titles


@pytest.mark.asyncio
async def test_tree_filter_inactive_nodes(ctx, tree_doctype):
    """filter[status__eq]=Inactive returns only Inactive nodes + their ancestors."""
    from grunt.core.document.tree import tree_service

    session = ctx.db._session()
    nodes = await tree_service.get_tree(
        session,
        "TreeCategory",
        filters={"status__eq": "Inactive"},
    )

    titles = _collect_titles(nodes)

    # Inactive nodes
    assert "Root-B" in titles
    assert "Child-A2" in titles

    # Root-A must appear as ancestor of Child-A2
    assert "Root-A" in titles

    # Active-only nodes must be absent
    assert "Child-A1" not in titles
    assert "Child-B1" not in titles


@pytest.mark.asyncio
async def test_tree_filter_no_match(ctx, tree_doctype):
    """filter that matches nothing returns an empty list."""
    from grunt.core.document.tree import tree_service

    session = ctx.db._session()
    nodes = await tree_service.get_tree(
        session,
        "TreeCategory",
        filters={"title__eq": "DoesNotExist"},
    )

    assert nodes == []


@pytest.mark.asyncio
async def test_tree_filter_by_title_ilike(ctx, tree_doctype):
    """filter[title__ilike]=child returns all child nodes + their parents."""
    from grunt.core.document.tree import tree_service

    session = ctx.db._session()
    nodes = await tree_service.get_tree(
        session,
        "TreeCategory",
        filters={"title__ilike": "%Child%"},
    )

    titles = _collect_titles(nodes)

    # All children match ilike
    assert "Child-A1" in titles
    assert "Child-A2" in titles
    assert "Child-B1" in titles

    # Parents appear as ancestors
    assert "Root-A" in titles
    assert "Root-B" in titles
