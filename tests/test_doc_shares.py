"""SharedWith grants: sharing one document gives one user access to it — and
nothing more (not other documents, not create/delete)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

BOX = {
    "name": "ShareBox",
    "label": "Share Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Editor", "read": True, "write": True},
    ],
}

BOB = "bob@example.com"


@pytest.fixture
async def boxes(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    for email in (BOB, "eve@example.com"):
        await ctx.new_doc("User", {"email": email, "first_name": "U", "last_name": "Ser"})
    a = (await ctx.new_doc("ShareBox", {"title": "A"}))["name"]
    b = (await ctx.new_doc("ShareBox", {"title": "B"}))["name"]
    await ctx.db._session().commit()
    return a, b


async def _share(ctx, doc: str, permission: str = "Read", user: str = BOB) -> str:
    row = await ctx.new_doc(
        "SharedWith",
        {
            "reference_doctype": "ShareBox",
            "reference_id": doc,
            "user": user,
            "permission": permission,
        },
    )
    await ctx.db._session().commit()
    return row["name"]


def _bob():
    return make_user(BOB, roles=[])


@pytest.mark.asyncio
async def test_no_share_no_access(ctx, boxes, db_session, engine):
    from grunt.app import grunt

    a, _ = boxes
    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises(HTTPException) as exc:
            await grunt.get_doc("ShareBox", a)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_read_share_grants_that_document_only(ctx, boxes, db_session, engine):
    from grunt.app import grunt

    a, b = boxes
    await _share(ctx, a, "Read")

    async with grunt.context(db_session, engine, _bob()):
        assert (await grunt.get_doc("ShareBox", a))["title"] == "A"
        assert [r["name"] for r in await grunt.get_list("ShareBox")] == [a]
        with pytest.raises(HTTPException):
            await grunt.get_doc("ShareBox", b)
        with pytest.raises(HTTPException):
            await grunt.save_doc("ShareBox", a, {"title": "A2"})


@pytest.mark.asyncio
async def test_write_share_allows_edit_but_not_delete_or_other_docs(ctx, boxes, db_session, engine):
    from grunt.app import grunt

    a, b = boxes
    await _share(ctx, a, "Write")

    async with grunt.context(db_session, engine, _bob()):
        assert (await grunt.save_doc("ShareBox", a, {"title": "A2"}))["title"] == "A2"
        with pytest.raises(HTTPException):
            await grunt.save_doc("ShareBox", b, {"title": "B2"})
        with pytest.raises(HTTPException):
            await grunt.delete_doc("ShareBox", a)


@pytest.mark.asyncio
async def test_unshare_revokes_access(ctx, boxes, db_session, engine):
    from grunt.app import grunt

    a, _ = boxes
    share = await _share(ctx, a, "Read")
    await ctx.delete_doc("SharedWith", share)
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises(HTTPException):
            await grunt.get_doc("ShareBox", a)
        # No role and no share left → the DocType itself is off-limits again.
        with pytest.raises(HTTPException):
            await grunt.get_list("ShareBox")


@pytest.mark.asyncio
async def test_only_writers_can_share(ctx, boxes, db_session, engine):
    from grunt.api.messages import ApplicationError
    from grunt.app import grunt

    a, _ = boxes
    await _share(ctx, a, "Read")  # bob can read A, not write it

    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.new_doc(
                "SharedWith",
                {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
            )

    editor = make_user("ed@example.com", roles=["Editor"])
    async with grunt.context(db_session, engine, editor):
        row = await grunt.new_doc(
            "SharedWith",
            {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
        )
    assert row["permission"] == "Read"


@pytest.mark.asyncio
async def test_share_to_unknown_user_rejected(ctx, boxes):
    from grunt.api.messages import ApplicationError

    a, _ = boxes
    with pytest.raises((ApplicationError, HTTPException)):
        await _share(ctx, a, "Read", user="ghost@example.com")


@pytest.mark.asyncio
async def test_share_rows_visible_to_grantee_and_sharer_only(ctx, boxes, db_session, engine):
    from grunt.app import grunt

    a, _ = boxes
    editor = make_user("ed@example.com", roles=["Editor"])
    async with grunt.context(db_session, engine, editor):
        await grunt.new_doc(
            "SharedWith", {"reference_doctype": "ShareBox", "reference_id": a, "user": BOB}
        )
    await db_session.commit()

    for who, expected in ((editor, 1), (_bob(), 1), (make_user("eve@example.com"), 0)):
        async with grunt.context(db_session, engine, who):
            try:
                rows = await grunt.get_list("SharedWith")
            except HTTPException:
                rows = []
        assert len(rows) == expected, who.email
