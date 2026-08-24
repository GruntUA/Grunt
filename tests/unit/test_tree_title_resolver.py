"""Tests for the TREE_TITLE_RESOLVERS extension point (grunt.document.tree).

Regression for moving Department's historical-title logic out of the
framework's generic api/v1/docs/tree.py (which used to hardcode
`if doctype == "Department"`) into hrm, reached via a doctype -> resolver
registry instead. These tests only exercise the registry/dispatch mechanism
itself (using a fake resolver) — Department's own resolver logic was moved
verbatim and isn't re-tested here.
"""

from __future__ import annotations

import pytest

from grunt.document.tree import TREE_TITLE_RESOLVERS, register_tree_title_resolver

RESOLVER_TREE_DOCTYPE = {
    "name": "ResolverTestTree",
    "label": "Resolver Test Tree",
    "module": "core",
    "is_tree": True,
    "tree_view": {"parent_field": "parent_node", "title_field": "title"},
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {
            "fieldname": "parent_node",
            "label": "Parent",
            "fieldtype": "Link",
            "options": "ResolverTestTree",
        },
    ],
    "permissions": [{"role": "All", "read": True, "write": True, "create": True}],
}


@pytest.fixture
async def resolver_tree_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**RESOLVER_TREE_DOCTYPE, "__is_new": True})
    root = await ctx.new_doc("ResolverTestTree", {"title": "Root"})
    await ctx.db._session().commit()
    return root


@pytest.fixture(autouse=True)
def _cleanup_registry():
    """TREE_TITLE_RESOLVERS is a module-level dict — don't leak between tests."""
    yield
    TREE_TITLE_RESOLVERS.pop("ResolverTestTree", None)


@pytest.mark.asyncio
async def test_get_tree_calls_registered_resolver_and_applies_titles(
    client, auth_headers, resolver_tree_doctype
):
    calls: list[tuple[str, str]] = []

    async def _fake_resolver(session, nodes, as_of):
        calls.append(("resolved", as_of))
        return {n["name"]: f"{n['title']} (as of {as_of})" for n in nodes}

    register_tree_title_resolver("ResolverTestTree", _fake_resolver)

    resp = await client.get(
        "/api/v1/method/grunt.document.base.Document.get_tree",
        params={"doctype": "ResolverTestTree", "as_of": "2024-01-15"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    nodes = resp.json()["data"]
    assert len(nodes) == 1
    assert nodes[0]["display_title"] == "Root (as of 2024-01-15)"
    assert calls == [("resolved", "2024-01-15")]


@pytest.mark.asyncio
async def test_get_tree_without_as_of_does_not_call_resolver(
    client, auth_headers, resolver_tree_doctype
):
    calls: list[str] = []

    async def _fake_resolver(session, nodes, as_of):
        calls.append(as_of)
        return {}

    register_tree_title_resolver("ResolverTestTree", _fake_resolver)

    resp = await client.get(
        "/api/v1/method/grunt.document.base.Document.get_tree",
        params={"doctype": "ResolverTestTree"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    nodes = resp.json()["data"]
    assert "display_title" not in nodes[0]
    assert calls == []


@pytest.mark.asyncio
async def test_get_tree_without_registered_resolver_ignores_as_of(
    client, auth_headers, resolver_tree_doctype
):
    """No resolver registered for this doctype — as_of is accepted but a no-op."""
    resp = await client.get(
        "/api/v1/method/grunt.document.base.Document.get_tree",
        params={"doctype": "ResolverTestTree", "as_of": "2024-01-15"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    nodes = resp.json()["data"]
    assert "display_title" not in nodes[0]
