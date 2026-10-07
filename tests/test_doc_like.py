"""DocLike and list badges: toggle like, per-page comment/like counts, only for
readable documents; likes die with the document."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

BOX = {
    "name": "LikeBox",
    "label": "Like Box",
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
    await ctx.new_doc("User", {"email": BOB, "first_name": "Bob", "last_name": "B"})
    names = [(await ctx.new_doc("LikeBox", {"title": t}))["name"] for t in ("A", "B")]
    await ctx.db._session().commit()
    return names


async def _as(db_session, engine, fn, user=None):
    import grunt

    async with grunt.context(db_session, engine, user or make_user(BOB, roles=["Editor"])):
        out = await fn()
    await db_session.commit()
    return out


@pytest.mark.asyncio
async def test_toggle_like(ctx, boxes, db_session, engine):
    from grunt.activity.likes import toggle_like

    a = boxes[0]
    assert await _as(db_session, engine, lambda: toggle_like("LikeBox", a)) == {
        "liked": True,
        "likes": 1,
    }
    assert await _as(db_session, engine, lambda: toggle_like("LikeBox", a)) == {
        "liked": False,
        "likes": 0,
    }


@pytest.mark.asyncio
async def test_list_badges_count_comments_and_likes(ctx, boxes, db_session, engine):
    from grunt.activity.likes import get_list_badges, toggle_like

    a, b = boxes
    await ctx.new_doc(
        "Comment", {"reference_doctype": "LikeBox", "reference_id": a, "content": "x"}
    )
    await ctx.new_doc(
        "Comment", {"reference_doctype": "LikeBox", "reference_id": a, "content": "y"}
    )
    await ctx.db._session().commit()
    await _as(db_session, engine, lambda: toggle_like("LikeBox", b))

    badges = await _as(db_session, engine, lambda: get_list_badges("LikeBox", [a, b]))
    assert badges[a] == {"comments": 2, "likes": 0, "liked": False}
    assert badges[b] == {"comments": 0, "likes": 1, "liked": True}


@pytest.mark.asyncio
async def test_badges_skip_unreadable(ctx, boxes, db_session, engine):
    from grunt.activity.likes import get_list_badges

    nobody = make_user(BOB, roles=[])
    with pytest.raises(HTTPException):
        await _as(db_session, engine, lambda: get_list_badges("LikeBox", boxes), nobody)


@pytest.mark.asyncio
async def test_cannot_like_unreadable(ctx, boxes, db_session, engine):
    from grunt.activity.likes import toggle_like

    with pytest.raises(HTTPException):
        await _as(
            db_session, engine, lambda: toggle_like("LikeBox", boxes[0]), make_user(BOB, roles=[])
        )


@pytest.mark.asyncio
async def test_likes_dropped_with_document(ctx, boxes, db_session, engine):
    from grunt.activity.likes import toggle_like

    await _as(db_session, engine, lambda: toggle_like("LikeBox", boxes[0]))
    await ctx.delete_doc("LikeBox", boxes[0])
    await ctx.db._session().commit()
    assert not await ctx.db.exists("DocLike", {"reference_id": boxes[0]})
