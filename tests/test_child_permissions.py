"""Child-table rows follow the access of their parent document."""

from __future__ import annotations

import pytest

from tests.support import make_user

ITEM = {
    "name": "CaseItem",
    "label": "Case Item",
    "module": "core",
    "is_child": True,
    "fields": [{"fieldname": "note", "label": "Note", "fieldtype": "Text"}],
}

CASE = {
    "name": "GuardedCase",
    "label": "Guarded Case",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "items", "label": "Items", "fieldtype": "Table", "options": "CaseItem"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Investigator", "read": True, "match": "owner == user"},
        {"role": "Editor", "read": True, "write": True},
    ],
}


@pytest.fixture
async def cases(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ITEM, "__is_new": True})
    await save_doctype(doctype_data={**CASE, "__is_new": True})
    mine = (await ctx.new_doc("GuardedCase", {"title": "Mine", "items": [{"note": "a"}]}))["name"]
    other = (await ctx.new_doc("GuardedCase", {"title": "Other", "items": [{"note": "b"}]}))["name"]
    await ctx.set_value("GuardedCase", mine, "owner", "ann@example.com")
    await ctx.db._session().commit()
    return mine, other


async def _row(ctx, parent: str) -> dict:
    [row] = await ctx.db.get_all("CaseItem", filters={"parent_name": parent}, fields=["*"])
    return row


@pytest.mark.asyncio
async def test_rows_readable_with_their_parent(ctx, cases, db_session, engine):
    import grunt
    from grunt.permissions.rbac import permission_checker

    mine, other = cases
    ann = make_user("ann@example.com", roles=["Investigator"])
    item = await grunt.get_meta("CaseItem")
    assert await permission_checker.check(ann, item, "read", await _row(ctx, mine))
    assert not await permission_checker.check(ann, item, "read", await _row(ctx, other))

    async with grunt.context(db_session, engine, ann):
        rows = await grunt.get_list("CaseItem", fields=["note", "parent_name"])
    assert [r["parent_name"] for r in rows] == [mine]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["write", "create", "delete"])
async def test_rows_change_only_through_the_parent(ctx, cases, action):
    """Even a parent writer can't touch rows directly - the parent's save
    (and its controller) is the only way in."""
    import grunt
    from grunt.permissions.rbac import permission_checker

    _, other = cases
    editor = make_user("ed@example.com", roles=["Editor"])
    item = await grunt.get_meta("CaseItem")
    doc = None if action == "create" else await _row(ctx, other)
    assert not await permission_checker.check(editor, item, action, doc)


@pytest.mark.asyncio
async def test_no_parent_access_closes_child_doctype(ctx, cases):
    import grunt
    from grunt.permissions.rbac import permission_checker

    stranger = make_user("x@example.com", roles=["Nobody"])
    item = await grunt.get_meta("CaseItem")
    assert not await permission_checker.check(stranger, item, "read")
