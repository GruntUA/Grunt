"""Replace-on-delete: repoint every reference to a surviving document, then delete.

Covers ``delete_doc(..., replace_with=...)`` and the bulk variant — Link fields
(top-level and inside child tables), tree self-references and the pre-flight
guards in ``validate_replacement``.
"""

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


TARGET_DT = {
    "name": "RplTarget",
    "label": "Rpl Target",
    "module": "core",
    "is_tree": True,
    "tree_parent_field": "parent_rpl",
    "title_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {"fieldname": "parent_rpl", "label": "Parent", "fieldtype": "Link", "options": "RplTarget"},
    ],
}

CHILD_DT = {
    "name": "RplLine",
    "label": "Rpl Line",
    "module": "core",
    "is_child": True,
    "fields": [
        {"fieldname": "ref", "label": "Ref", "fieldtype": "Link", "options": "RplTarget"},
    ],
}

SOURCE_DT = {
    "name": "RplSource",
    "label": "Rpl Source",
    "module": "core",
    "fields": [
        {"fieldname": "ref", "label": "Ref", "fieldtype": "Link", "options": "RplTarget"},
        {"fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "RplLine"},
    ],
}


@pytest.fixture
async def rpl_doctypes(ctx):
    from grunt.api.v1.meta import save_doctype

    for data in (TARGET_DT, CHILD_DT, SOURCE_DT):
        await save_doctype(doctype_data={**data, "__is_new": True})
    await ctx.db._session().commit()


async def test_delete_with_replacement_repoints_links(ctx, rpl_doctypes):
    """A replacement id repoints the top-level Link and the child-table Link."""
    a = await ctx.new_doc("RplTarget", {"title": "A"})
    b = await ctx.new_doc("RplTarget", {"title": "B"})
    src = await ctx.new_doc(
        "RplSource", {"ref": a["name"], "lines": [{"ref": a["name"]}]}
    )
    await ctx.db._session().commit()

    await ctx.delete_doc("RplTarget", a["name"], b["name"])
    await ctx.db._session().commit()

    with pytest.raises(HTTPException):
        await ctx.get_doc("RplTarget", a["name"])

    refetched = await ctx.get_doc("RplSource", src["name"])
    assert refetched["ref"] == b["name"]
    assert refetched["lines"][0]["ref"] == b["name"]


async def test_delete_replacement_reparents_children(ctx, rpl_doctypes):
    """Children of the deleted tree node move under the replacement."""
    old = await ctx.new_doc("RplTarget", {"title": "Old"})
    new = await ctx.new_doc("RplTarget", {"title": "New"})
    kid = await ctx.new_doc("RplTarget", {"title": "Kid", "parent_rpl": old["name"]})
    await ctx.db._session().commit()

    await ctx.delete_doc("RplTarget", old["name"], new["name"])
    await ctx.db._session().commit()

    assert (await ctx.get_doc("RplTarget", kid["name"]))["parent_rpl"] == new["name"]


async def test_delete_replacement_rejects_descendant(ctx, rpl_doctypes):
    """Can't hand a branch to one of its own descendants."""
    parent = await ctx.new_doc("RplTarget", {"title": "P"})
    child = await ctx.new_doc("RplTarget", {"title": "C", "parent_rpl": parent["name"]})
    await ctx.db._session().commit()

    with pytest.raises(HTTPException) as exc_info:
        await ctx.delete_doc("RplTarget", parent["name"], child["name"])
    assert exc_info.value.status_code == 400


async def test_delete_replacement_rejects_missing_and_self(ctx, rpl_doctypes):
    a = await ctx.new_doc("RplTarget", {"title": "A"})
    await ctx.db._session().commit()

    with pytest.raises(HTTPException) as exc_info:
        await ctx.delete_doc("RplTarget", a["name"], "does-not-exist")
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        await ctx.delete_doc("RplTarget", a["name"], a["name"])
    assert exc_info.value.status_code == 400


async def test_get_delete_impact_counts(ctx, rpl_doctypes):
    """Impact scan counts Link refs in top-level and child tables."""
    from grunt.document.links import link_service

    a = await ctx.new_doc("RplTarget", {"title": "A"})
    await ctx.new_doc("RplSource", {"ref": a["name"], "lines": [{"ref": a["name"]}]})
    await ctx.new_doc("RplSource", {"ref": a["name"]})
    await ctx.db._session().commit()

    impact = await link_service.get_delete_impact(
        ctx.db._session(), "RplTarget", [a["name"]]
    )
    assert impact["total"] == 3
    by_key = {(g["doctype"], g["field"]): g for g in impact["groups"]}
    assert by_key[("RplSource", "ref")]["count"] == 2
    assert by_key[("RplLine", "ref")]["count"] == 1
    assert by_key[("RplLine", "ref")]["in_child"] is True
    assert by_key[("RplLine", "ref")]["parent_doctype"] == "RplSource"


async def test_get_delete_impact_rpc(ctx, rpl_doctypes):
    """The whitelisted RPC wrapper does its own per-id permission check."""
    from grunt.document.base import Document

    a = await ctx.new_doc("RplTarget", {"title": "A"})
    await ctx.new_doc("RplSource", {"ref": a["name"]})
    await ctx.db._session().commit()

    impact = await Document.get_delete_impact("RplTarget", doc_id=a["name"])
    assert impact["total"] == 1

    impact = await Document.get_delete_impact("RplTarget", doc_ids=[a["name"]])
    assert impact["total"] == 1


async def test_bulk_delete_with_replacement(ctx, rpl_doctypes):
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    a = await ctx.new_doc("RplTarget", {"title": "A"})
    b = await ctx.new_doc("RplTarget", {"title": "B"})
    keep = await ctx.new_doc("RplTarget", {"title": "Keep"})
    src_a = await ctx.new_doc("RplSource", {"ref": a["name"]})
    src_b = await ctx.new_doc("RplSource", {"ref": b["name"]})
    await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        deleted, errors = await ctx.bulk_delete_docs(
            "RplTarget", [a["name"], b["name"]], replace_with=keep["name"]
        )
        await ctx.db._session().commit()

    assert deleted == 2
    assert not errors
    assert (await ctx.get_doc("RplSource", src_a["name"]))["ref"] == keep["name"]
    assert (await ctx.get_doc("RplSource", src_b["name"]))["ref"] == keep["name"]


async def test_delete_without_replacement_leaves_dangling_ref(ctx, rpl_doctypes):
    """No replacement — deletion still succeeds, the ref is left pointing at a gone id."""
    a = await ctx.new_doc("RplTarget", {"title": "A"})
    src = await ctx.new_doc("RplSource", {"ref": a["name"]})
    await ctx.db._session().commit()

    await ctx.delete_doc("RplTarget", a["name"])
    await ctx.db._session().commit()

    assert (await ctx.get_doc("RplSource", src["name"]))["ref"] == a["name"]
