"""Tests for tree filtering via GET /docs/{doctype}/tree.

Verifies that filter[field__op]=value params correctly prune the tree
to matching nodes + their ancestors.
"""

from __future__ import annotations

import pytest

from tests.support import make_user

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


def _root_titles(nodes: list[dict]) -> list[str]:
    return [str(n.get("title") or "") for n in nodes]


def _child_titles(nodes: list[dict], root_title: str) -> list[str]:
    for node in nodes:
        if node.get("title") == root_title:
            return [str(c.get("title") or "") for c in (node.get("children") or [])]
    return []


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tree_filter_active_nodes(ctx, tree_doctype):
    """filter[status__eq]=Active returns Active nodes + their ancestors."""
    from grunt.document.tree import tree_service

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
    from grunt.document.tree import tree_service

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
    from grunt.document.tree import tree_service

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
    from grunt.document.tree import tree_service

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


@pytest.mark.asyncio
async def test_tree_sort_by_query_params(ctx, tree_doctype):
    """Explicit sort_by/sort_order sorts root level in tree output."""
    from grunt.document.tree import tree_service

    session = ctx.db._session()
    nodes = await tree_service.get_tree(
        session,
        "TreeCategory",
        sort_by="title",
        sort_order="desc",
    )

    assert _root_titles(nodes) == ["Root-B", "Root-A"]


@pytest.mark.asyncio
async def test_tree_children_sort_by_query_params(ctx, tree_doctype):
    """get_children applies the same optional sort params contract."""
    from grunt.document.tree import tree_service

    session = ctx.db._session()
    root_a_name = tree_doctype["root_a"]["name"]
    children = await tree_service.get_children(
        session,
        "TreeCategory",
        parent_id=root_a_name,
        sort_by="title",
        sort_order="desc",
    )

    assert [c["title"] for c in children] == ["Child-A2", "Child-A1"]


@pytest.mark.asyncio
async def test_tree_ancestors_ordered_root_first_excludes_self(ctx, tree_doctype):
    """get_ancestors returns the path from root down to the direct parent.

    Regression: get_ancestors was rewritten from a hand-built recursive
    ``WITH RECURSIVE`` string to a SQLAlchemy Core recursive CTE
    (``Select.cte(recursive=True)``) — this pins down ordering (root first,
    direct parent last) and that the queried node itself is excluded.
    """
    from grunt.document.tree import tree_service

    session = ctx.db._session()
    root_a = tree_doctype["root_a"]
    child_a1 = tree_doctype["child_a1"]

    grandchild = await ctx.new_doc(
        "TreeCategory",
        {"title": "Grandchild-A1a", "status": "Active", "parent_category": child_a1["name"]},
    )
    await ctx.db._session().commit()

    ancestors = await tree_service.get_ancestors(session, "TreeCategory", grandchild["name"])

    assert [a["title"] for a in ancestors] == ["Root-A", "Child-A1"]
    assert all(a["name"] != grandchild["name"] for a in ancestors)
    assert all(a["name"] != root_a["name"] or a["title"] == "Root-A" for a in ancestors)


@pytest.mark.asyncio
async def test_tree_ancestors_root_node_returns_empty(ctx, tree_doctype):
    """A root node has no ancestors."""
    from grunt.document.tree import tree_service

    session = ctx.db._session()
    root_a = tree_doctype["root_a"]

    ancestors = await tree_service.get_ancestors(session, "TreeCategory", root_a["name"])

    assert ancestors == []


@pytest.mark.asyncio
async def test_tree_sort_override_via_document_controller(ctx, tree_doctype):
    """Third-party controllers can override tree sorting via Document virtual methods."""
    from typing import Any

    from grunt.document.base import Document
    from grunt.document.registry import document_registry
    from grunt.document.tree import tree_service

    class TreeCategoryController(Document):
        @classmethod
        async def tree_get_sort_order(
            cls,
            session: Any,
            filters: dict[str, Any],
            table: Any,
            *,
            sort_by: str | None,
            sort_order: str,
        ) -> tuple[str | None, str] | None:
            return ("title", "desc")

    previous = document_registry._controllers.get("TreeCategory")
    document_registry.register("TreeCategory", TreeCategoryController)

    try:
        session = ctx.db._session()
        nodes = await tree_service.get_tree(session, "TreeCategory")
        assert _root_titles(nodes) == ["Root-B", "Root-A"]

        root_a_name = tree_doctype["root_a"]["name"]
        children = await tree_service.get_children(
            session,
            "TreeCategory",
            parent_id=root_a_name,
        )
        assert [c["title"] for c in children] == ["Child-A2", "Child-A1"]
    finally:
        if previous is None:
            document_registry._controllers.pop("TreeCategory", None)
        else:
            document_registry.register("TreeCategory", previous)


# ── Regression: docs/tree.py router endpoints used to have NO doctype-level
# permission check at all — any authenticated user could read/reorder tree
# data for any doctype regardless of DocTypePermission. TreeCategory (above)
# has no `permissions` defined, so per the framework's "no permissions = open
# (dev mode)" convention it can't prove the gate works — these tests use a
# doctype with real restrictive permissions instead. ─────────────────────────

GUARDED_TREE_DOCTYPE = {
    "name": "GuardedTreeCategory",
    "label": "Guarded Tree Category",
    "module": "core",
    "is_tree": True,
    "tree_view": {"parent_field": "parent_category", "title_field": "title"},
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {
            "fieldname": "parent_category",
            "label": "Parent Category",
            "fieldtype": "Link",
            "options": "GuardedTreeCategory",
        },
    ],
    "permissions": [{"role": "TreeManager", "read": True, "write": True, "create": True}],
}


@pytest.fixture
async def guarded_tree_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**GUARDED_TREE_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()

    root = await ctx.new_doc("GuardedTreeCategory", {"title": "Root"})
    child = await ctx.new_doc(
        "GuardedTreeCategory", {"title": "Child", "parent_category": root["name"]}
    )
    await ctx.db._session().commit()
    return {"root": root, "child": child}


@pytest.mark.asyncio
async def test_get_tree_denies_user_without_role(ctx, guarded_tree_doctype):
    from fastapi import HTTPException

    from grunt.document.base import Document

    outsider = make_user("outsider@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx._require_engine(), outsider):
        with pytest.raises(HTTPException) as excinfo:
            await Document.get_tree("GuardedTreeCategory")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_get_tree_allows_user_with_role(ctx, guarded_tree_doctype):
    from grunt.document.base import Document

    manager = make_user("tree-manager@grunt.example.com", roles=["TreeManager"])
    async with ctx.context(ctx.db._session(), ctx._require_engine(), manager):
        result = await Document.get_tree("GuardedTreeCategory")
    assert _root_titles(result) == ["Root"]


@pytest.mark.asyncio
async def test_get_children_denies_user_without_role(ctx, guarded_tree_doctype):
    from fastapi import HTTPException

    from grunt.document.base import Document

    outsider = make_user("outsider2@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx._require_engine(), outsider):
        with pytest.raises(HTTPException) as excinfo:
            await Document.get_tree_children("GuardedTreeCategory")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_get_ancestors_denies_user_without_role(ctx, guarded_tree_doctype):
    from fastapi import HTTPException

    from grunt.document.base import Document

    outsider = make_user("outsider3@grunt.example.com")
    child_name = guarded_tree_doctype["child"]["name"]
    async with ctx.context(ctx.db._session(), ctx._require_engine(), outsider):
        with pytest.raises(HTTPException) as excinfo:
            await Document.get_tree_ancestors("GuardedTreeCategory", child_name)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_move_node_denies_user_without_write_role(ctx, guarded_tree_doctype):
    from fastapi import HTTPException

    from grunt.document.base import Document

    outsider = make_user("outsider4@grunt.example.com")
    child_name = guarded_tree_doctype["child"]["name"]
    async with ctx.context(ctx.db._session(), ctx._require_engine(), outsider):
        with pytest.raises(HTTPException) as excinfo:
            await Document.move_tree_node("GuardedTreeCategory", child_name, new_parent_id=None)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_move_node_allows_user_with_write_role(ctx, guarded_tree_doctype):
    from grunt.document.base import Document

    manager = make_user("tree-manager2@grunt.example.com", roles=["TreeManager"])
    child_name = guarded_tree_doctype["child"]["name"]
    async with ctx.context(ctx.db._session(), ctx._require_engine(), manager):
        result = await Document.move_tree_node(
            "GuardedTreeCategory", child_name, new_parent_id=None
        )
    assert result["parent_category"] is None
