"""CommentReaction: toggle an emoji on a comment, summaries in the timeline, only
configured emoji, only on readable documents; reactions die with the comment."""

import pytest
from fastapi import HTTPException

from tests.support import make_user

BOX = {
    "name": "ReactBox",
    "label": "React Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Editor", "read": True, "write": True},
    ],
}

BOB = "bob@example.com"


@pytest.fixture
async def comment(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    await ctx.new_doc("User", {"email": BOB, "first_name": "Bob", "last_name": "B"})
    box = await ctx.new_doc("ReactBox", {"title": "A"})
    c = await ctx.new_doc(
        "Comment", {"reference_doctype": "ReactBox", "reference_id": box["name"], "content": "x"}
    )
    await ctx.db._session().commit()
    return box["name"], str(c["name"])


async def _as(db_session, engine, fn, user=None):
    import grunt

    async with grunt.context(db_session, engine, user or make_user(BOB, roles=["Editor"])):
        out = await fn()
    await db_session.commit()
    return out


@pytest.mark.asyncio
async def test_toggle_reaction(ctx, comment, db_session, engine):
    from grunt.activity.reactions import toggle_reaction

    _, c = comment
    on = await _as(db_session, engine, lambda: toggle_reaction(c, "👍"))
    assert on == [{"emoji": "👍", "count": 1, "mine": True, "users": ["B Bob"]}]
    assert await _as(db_session, engine, lambda: toggle_reaction(c, "👍")) == []


@pytest.mark.asyncio
async def test_reactions_in_timeline(ctx, comment, db_session, engine):
    from grunt.activity.reactions import toggle_reaction
    from grunt.document.base import Document

    box, c = comment
    await _as(db_session, engine, lambda: toggle_reaction(c, "✅"))
    await _as(db_session, engine, lambda: toggle_reaction(c, "👍"))
    items = await _as(db_session, engine, lambda: Document.get_timeline("ReactBox", box))
    item = next(i for i in items if i["type"] == "comment")
    # Ordered as the choices are, not as they were added.
    assert [r["emoji"] for r in item["reactions"]] == ["👍", "✅"]


@pytest.mark.asyncio
async def test_unknown_emoji_rejected(ctx, comment, db_session, engine):
    from grunt.activity.reactions import toggle_reaction

    with pytest.raises(HTTPException):
        await _as(db_session, engine, lambda: toggle_reaction(comment[1], "💩"))


@pytest.mark.asyncio
async def test_cannot_react_on_unreadable(ctx, comment, db_session, engine):
    from grunt.activity.reactions import toggle_reaction

    nobody = make_user(BOB, roles=[])
    with pytest.raises(HTTPException):
        await _as(db_session, engine, lambda: toggle_reaction(comment[1], "👍"), nobody)


@pytest.mark.asyncio
async def test_reactions_dropped_with_comment(ctx, comment, db_session, engine):
    from grunt.activity.reactions import toggle_reaction

    _, c = comment
    await _as(db_session, engine, lambda: toggle_reaction(c, "👍"))
    await ctx.delete_doc("Comment", c)
    await ctx.db._session().commit()
    assert not await ctx.db.exists("CommentReaction", {"comment": c})
