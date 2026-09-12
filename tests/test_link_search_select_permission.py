"""Integration: the ``select`` permission lets a Link-field picker resolve a
DocType (name / title / search fields) without granting ``read`` — no list
access, no full-document read, no field unmasking."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

CATALOG = {
    "name": "LSCatalog",
    "label": "LS Catalog",
    "module": "core",
    "title_field": "title",
    "search_fields": ["code"],
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "code", "label": "Code", "fieldtype": "Data"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "Picker", "select": True},
    ],
}


@pytest.fixture
async def setup_catalog(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**CATALOG, "__is_new": True})
    for i, t in enumerate(["Alpha", "Beta", "Gamma"]):
        await ctx.new_doc("LSCatalog", {"title": t, "code": f"C{i}", "secret": f"top{i}"})
    await ctx.db._session().commit()


def _picker(email: str) -> User:
    return make_user(email, roles=["Picker"])


@pytest.mark.asyncio
async def test_select_only_user_can_search_link(ctx, setup_catalog, db_session, engine):
    from grunt.app import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, _picker("p@example.com")):
        hits = await Document.link_search("LSCatalog", search="Bet")
        assert [h["title"] for h in hits] == ["Beta"]

        # search field also works
        hits = await Document.link_search("LSCatalog", search="C2")
        assert [h["name"] for h in hits][:1] and hits[0]["title"] == "Gamma"

        # ...but list and full read stay denied
        with pytest.raises(HTTPException) as e:
            await grunt.get_list("LSCatalog")
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            await grunt.get_doc("LSCatalog", hits[0]["name"])
        assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_no_select_no_read_denies_link_search(ctx, setup_catalog, db_session, engine):
    from grunt.app import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("x@example.com", roles=[])):
        with pytest.raises(HTTPException) as e:
            await Document.link_search("LSCatalog", search="Alpha")
        assert e.value.status_code == 403


MIXED = {
    "name": "LSMixedCat",
    "label": "LS Mixed Catalog",
    "module": "core",
    "title_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Data"},
    ],
    # A row-scoped "read" for everyone PLUS an explicit "select" for one role.
    "permissions": [
        {"role": "All", "read": True, "match": "owner == user"},
        {"role": "Picker", "select": True},
    ],
}


@pytest.fixture
async def setup_mixed(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**MIXED, "__is_new": True})
    for i, t in enumerate(["Alpha", "Beta", "Gamma"]):
        await ctx.new_doc("LSMixedCat", {"title": t, "secret": f"top{i}"})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_explicit_select_beats_row_scoped_read(ctx, setup_mixed, db_session, engine):
    """An explicit ``select`` grant gives an unfiltered identifier picker even
    when the caller also matches a row-scoped ``read`` rule (here: owns none of
    the rows, so the plain "read" path would return nothing)."""
    from grunt.app import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, _picker("outsider@example.com")):
        hits = await Document.link_search("LSMixedCat", search="")
        assert sorted(h["title"] for h in hits) == ["Alpha", "Beta", "Gamma"]
        assert all("secret" not in h for h in hits)


@pytest.mark.asyncio
async def test_row_scoped_read_without_select_still_filters(ctx, setup_mixed, db_session, engine):
    """No ``select`` grant → the picker keeps the legacy row-filtered "read"
    path (no 403, just the caller's own subset — empty here)."""
    from grunt.app import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("nobody@example.com", roles=[])):
        hits = await Document.link_search("LSMixedCat", search="")
        assert hits == []


LSTREE = {
    "name": "LSUnit",
    "label": "LS Unit",
    "module": "core",
    "is_tree": True,
    "tree_parent_field": "parent_unit",
    "autoname": "field:title",
    "title_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "parent_unit", "label": "Parent", "fieldtype": "Link", "options": "LSUnit"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Data"},
    ],
    "permissions": [{"role": "Picker", "select": True}],
}


@pytest.mark.asyncio
async def test_select_only_user_can_load_tree_picker(ctx, db_session, engine):
    from grunt.api.v1.meta import save_doctype
    from grunt.app import grunt
    from grunt.document.base import Document

    await save_doctype(doctype_data={**LSTREE, "__is_new": True})
    await ctx.new_doc("LSUnit", {"title": "Root", "secret": "s0"})
    await ctx.new_doc("LSUnit", {"title": "Child", "parent_unit": "Root", "secret": "s1"})
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _picker("p@example.com")):
        tree = await Document.get_tree("LSUnit")
        assert [n["name"] for n in tree] == ["Root"]
        assert [c["name"] for c in tree[0]["children"]] == ["Child"]
        assert "secret" not in tree[0]  # identifier columns only

        with pytest.raises(HTTPException) as e:
            await grunt.get_list("LSUnit")
        assert e.value.status_code == 403

    async with grunt.context(db_session, engine, make_user("z@example.com", roles=[])):
        with pytest.raises(HTTPException) as e:
            await Document.get_tree("LSUnit")
        assert e.value.status_code == 403
