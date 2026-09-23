"""DocFollow: followers are notified about updates and comments, never about
their own actions; you can follow only what you can read; follows die with the doc."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

BOX = {
    "name": "FollowBox",
    "label": "Follow Box",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "qty", "label": "Quantity", "fieldtype": "Int"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Editor", "read": True, "write": True},
    ],
}

BOB = "bob@example.com"


@pytest.fixture
async def box(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    await ctx.new_doc("User", {"email": BOB, "first_name": "Bob", "last_name": "B"})
    name = (await ctx.new_doc("FollowBox", {"title": "Box", "qty": 1}))["name"]
    await ctx.db._session().commit()
    return name


async def _follow(db_session, engine, doc: str, user=None) -> dict:
    from grunt.app import grunt

    async with grunt.context(db_session, engine, user or make_user(BOB, roles=["Editor"])):
        row = await grunt.new_doc(
            "DocFollow", {"reference_doctype": "FollowBox", "reference_id": doc, "user": "x@y.z"}
        )
    await db_session.commit()
    return row


async def _notifications(ctx, user: str) -> list[dict]:
    return await ctx.db.get_all(
        "Notification", filters={"user": user}, fields=["subject", "message"], limit=None
    )


@pytest.mark.asyncio
async def test_follow_is_always_for_yourself(ctx, box, db_session, engine):
    row = await _follow(db_session, engine, box)
    assert row["user"] == BOB


@pytest.mark.asyncio
async def test_update_notifies_follower_with_changed_fields(ctx, box, db_session, engine):
    await _follow(db_session, engine, box)

    await ctx.save_doc("FollowBox", box, {"qty": 5})
    await ctx.db._session().commit()

    [n] = await _notifications(ctx, BOB)
    assert "змінено" in n["subject"]
    assert "Quantity" in n["message"]


@pytest.mark.asyncio
async def test_own_changes_do_not_notify(ctx, box, db_session, engine):
    from grunt.app import grunt

    bob = make_user(BOB, roles=["Editor"])
    await _follow(db_session, engine, box, bob)
    async with grunt.context(db_session, engine, bob):
        await grunt.save_doc("FollowBox", box, {"qty": 9})
    await db_session.commit()

    assert await _notifications(ctx, BOB) == []


@pytest.mark.asyncio
async def test_comment_notifies_follower(ctx, box, db_session, engine):
    await _follow(db_session, engine, box)

    await ctx.new_doc(
        "Comment",
        {"reference_doctype": "FollowBox", "reference_id": box, "content": "Перевірте кількість"},
    )
    await ctx.db._session().commit()

    [n] = await _notifications(ctx, BOB)
    assert "коментар" in n["subject"]
    assert "Перевірте кількість" in n["message"]


@pytest.mark.asyncio
async def test_cannot_follow_unreadable_document(ctx, box, db_session, engine):
    from grunt.api.messages import ApplicationError

    with pytest.raises((ApplicationError, HTTPException)):
        await _follow(db_session, engine, box, make_user(BOB, roles=[]))


@pytest.mark.asyncio
async def test_duplicate_follow_rejected(ctx, box, db_session, engine):
    from grunt.api.messages import ApplicationError

    await _follow(db_session, engine, box)
    with pytest.raises((ApplicationError, HTTPException)):
        await _follow(db_session, engine, box)


@pytest.mark.asyncio
async def test_follows_dropped_with_document(ctx, box, db_session, engine):
    await _follow(db_session, engine, box)
    await ctx.delete_doc("FollowBox", box)
    await ctx.db._session().commit()

    assert not await ctx.db.exists("DocFollow", {"reference_id": box})
