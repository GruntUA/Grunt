"""Comment threads: replies are one level deep, stay on their document, notify
the thread's author, and a thread with others' replies is deleted only by an admin."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from tests.support import make_user

BOX = {
    "name": "ThreadBox",
    "label": "Thread Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Editor", "read": True, "write": True},
    ],
}

ALICE = "alice@example.com"
BOB = "bob@example.com"
ERRORS = (ApplicationError, HTTPException)


@pytest.fixture
async def boxes(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    for email, first in ((ALICE, "Alice"), (BOB, "Bob")):
        await ctx.new_doc("User", {"email": email, "first_name": first, "last_name": "T"})
    names = [(await ctx.new_doc("ThreadBox", {"title": t}))["name"] for t in ("A", "B")]
    await ctx.db._session().commit()
    return names


@pytest.fixture
def comment(db_session, engine):
    """add_comment as *user* (an Editor unless roles are given)."""
    import grunt
    from grunt.document.base import Document

    async def add(email, box, text, parent=None, roles=("Editor",)):
        async with grunt.context(db_session, engine, make_user(email, roles=list(roles))):
            row = await Document.add_comment(
                doctype="ThreadBox", doc_id=box, content=text, parent_comment=parent
            )
        await db_session.commit()
        return row

    return add


async def _subjects(ctx, user):
    rows = await ctx.db.get_all("Notification", filters={"user": user}, fields=["subject"])
    return [r["subject"] for r in rows]


@pytest.mark.asyncio
async def test_reply_and_flattening(ctx, boxes, comment):
    root = await comment(ALICE, boxes[0], "Перевірте суму")
    reply = await comment(BOB, boxes[0], "Перевірив", parent=root["name"])
    assert reply["parent_comment"] == root["name"]

    # A reply to a reply joins the root's thread.
    nested = await comment(ALICE, boxes[0], "Дякую", parent=reply["name"])
    assert nested["parent_comment"] == root["name"]


@pytest.mark.asyncio
async def test_reply_must_stay_on_the_document(ctx, boxes, comment):
    root = await comment(ALICE, boxes[0], "Root")
    with pytest.raises(ERRORS):
        await comment(BOB, boxes[1], "Elsewhere", parent=root["name"])
    with pytest.raises(ERRORS):
        await comment(BOB, boxes[0], "Ghost", parent="does-not-exist")


@pytest.mark.asyncio
async def test_reply_notifies_thread_author_once(ctx, boxes, comment):
    from grunt import _

    root = await comment(ALICE, boxes[0], "Root")
    await comment(BOB, boxes[0], "Reply", parent=root["name"])
    replied = _("%(user)s replied to your comment") % {"user": BOB}
    assert await _subjects(ctx, ALICE) == [replied]

    # Mentioned in the reply -> only the mention notification, not both.
    await comment(BOB, boxes[0], f"@{ALICE} глянь", parent=root["name"])
    assert len(await _subjects(ctx, ALICE)) == 2

    # Replying in your own thread notifies nobody.
    await comment(ALICE, boxes[0], "Self", parent=root["name"])
    assert len(await _subjects(ctx, ALICE)) == 2


@pytest.mark.asyncio
async def test_timeline_carries_parent(ctx, boxes, comment, db_session, engine):
    import grunt
    from grunt.document.base import Document

    root = await comment(ALICE, boxes[0], "Root")
    await comment(BOB, boxes[0], "Reply", parent=root["name"])
    async with grunt.context(db_session, engine, make_user(ALICE, roles=["Editor"])):
        items = await Document.get_timeline(doctype="ThreadBox", doc_id=boxes[0])
    parents = {i["content"]: i["parent_comment"] for i in items if i["type"] == "comment"}
    assert parents == {"Root": None, "Reply": root["name"]}


@pytest.mark.asyncio
async def test_deleting_threads(ctx, boxes, comment, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async def delete(email, name, roles=("Editor",)):
        async with grunt.context(db_session, engine, make_user(email, roles=list(roles))):
            await Document.delete_comment(doctype="ThreadBox", doc_id=boxes[0], comment_id=name)
        await db_session.commit()

    async def remaining():
        rows = await ctx.db.get_all("Comment", filters={"reference_id": boxes[0]}, fields=["name"])
        return {r["name"] for r in rows}

    # Only own replies -> the author may delete the whole thread.
    own = await comment(ALICE, boxes[0], "Own thread")
    own_reply = await comment(ALICE, boxes[0], "Own reply", parent=own["name"])
    await delete(ALICE, own["name"])
    assert not {own["name"], own_reply["name"]} & await remaining()

    # Someone else replied -> the author cannot, an admin can (with the replies).
    root = await comment(ALICE, boxes[0], "Root")
    reply = await comment(BOB, boxes[0], "Bob's reply", parent=root["name"])
    with pytest.raises(ERRORS):
        await delete(ALICE, root["name"])
    await db_session.rollback()
    assert {root["name"], reply["name"]} <= await remaining()

    # A reply on its own is the author's to delete.
    await delete(BOB, reply["name"])
    assert reply["name"] not in await remaining()

    second = await comment(BOB, boxes[0], "Again", parent=root["name"])
    await delete("admin@example.com", root["name"], roles=("System Manager",))
    assert not {root["name"], second["name"]} & await remaining()
