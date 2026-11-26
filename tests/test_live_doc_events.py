"""``grunt.activity.live`` - an open form and its timeline hear about changes.

After the commit, into the document's room only: ``doc_change`` when the
document is saved or deleted, ``timeline_change`` when a comment, reaction,
file or assignment of it changes.
"""

import pytest

from grunt.api.v1.ws import manager
from grunt.db.commit import drain

LIVE_DOCTYPE = {
    "name": "LiveItem",
    "label": "Live Item",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
}


@pytest.fixture
async def sent(ctx, monkeypatch):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LIVE_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()
    await drain()

    events: list[tuple[str, str, str, dict]] = []

    async def record(doctype, doc_id, event, data):
        events.append((doctype, doc_id, event, data))

    monkeypatch.setattr(manager, "broadcast_doc", record)
    return events


async def _commit(ctx) -> None:
    await ctx.db._session().commit()
    await drain()


def _of(events, doctype: str, doc_id: str) -> list[tuple[str, dict]]:
    return [(e, d) for dt, i, e, d in events if (dt, i) == (doctype, doc_id)]


@pytest.mark.asyncio
async def test_save_sends_doc_change_after_commit(ctx, sent):
    doc = await ctx.new_doc("LiveItem", {"title": "A"})
    await drain()
    assert _of(sent, "LiveItem", doc.name) == []  # still uncommitted

    await _commit(ctx)
    [(event, data)] = _of(sent, "LiveItem", doc.name)
    assert event == "doc_change"
    assert data["source"] == "save"
    assert data["modified_at"]

    sent.clear()
    await ctx.save_doc("LiveItem", doc.name, {"title": "B"})
    await _commit(ctx)
    assert [e for e, _ in _of(sent, "LiveItem", doc.name)] == ["doc_change"]


@pytest.mark.asyncio
async def test_rollback_sends_nothing(ctx, sent):
    doc = await ctx.new_doc("LiveItem", {"title": "A"})
    await ctx.db._session().rollback()
    await drain()
    assert _of(sent, "LiveItem", doc.name) == []


@pytest.mark.asyncio
async def test_timeline_items_go_to_their_document(ctx, sent):
    doc = await ctx.new_doc("LiveItem", {"title": "A"})
    await _commit(ctx)
    sent.clear()

    comment = await ctx.new_doc(
        "Comment",
        {
            "reference_doctype": "LiveItem",
            "reference_id": doc.name,
            "comment_type": "Comment",
            "content": "hi",
        },
    )
    await ctx.new_doc(
        "ToDo",
        {"description": "do it", "reference_doctype": "LiveItem", "reference_id": doc.name},
    )
    await _commit(ctx)
    # One event per kind and transaction; the items get no room event of their own.
    assert _of(sent, "LiveItem", doc.name) == [("timeline_change", {"source": "Comment"})]
    assert _of(sent, "Comment", comment.name) == []

    sent.clear()
    await ctx.delete_doc("Comment", comment.name)
    await _commit(ctx)
    assert [e for e, _ in _of(sent, "LiveItem", doc.name)] == ["timeline_change"]


@pytest.mark.asyncio
async def test_reaction_goes_to_the_comments_document(ctx, sent):
    from grunt.activity.reactions import toggle_reaction

    doc = await ctx.new_doc("LiveItem", {"title": "A"})
    comment = await ctx.new_doc(
        "Comment",
        {"reference_doctype": "LiveItem", "reference_id": doc.name, "content": "hi"},
    )
    await _commit(ctx)
    sent.clear()

    await toggle_reaction(comment.name, "👍")
    await _commit(ctx)
    assert _of(sent, "LiveItem", doc.name) == [("timeline_change", {"source": "CommentReaction"})]


@pytest.mark.asyncio
async def test_delete_sends_doc_change(ctx, sent):
    doc = await ctx.new_doc("LiveItem", {"title": "A"})
    await _commit(ctx)
    sent.clear()

    await ctx.delete_doc("LiveItem", doc.name)
    await _commit(ctx)
    [(event, data)] = _of(sent, "LiveItem", doc.name)
    assert (event, data["source"]) == ("doc_change", "delete")
