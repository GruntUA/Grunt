"""Workflow rules - review/approval out of the box (grunt/workflow/guard.py, notify.py).

An author drafts and sends for review; a reviewer publishes or sends back with
a comment; an author's edit of a published article sends it back to review.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException

import grunt

AUTHOR = "author@grunt.example.com"
REVIEWER = "reviewer@grunt.example.com"
# The reviewer's account id differs from their email (the email was changed later).
REVIEWER_ID = "first-email@grunt.example.com"
READER = "reader@grunt.example.com"

ARTICLE = {
    "name": "Article",
    "label": "Article",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Text"},
        {"fieldname": "published", "label": "Published", "fieldtype": "Check"},
    ],
    "permissions": [
        {"role": "Writer", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Editor", "read": True, "write": True, "create": True, "delete": True},
    ],
}
W, E = "Writer", "Editor"
WORKFLOW = {
    "document_type": "Article",
    "workflow_state_field": "status",
    "states": [
        {"state": "Draft", "is_initial": True, "update_field": "published", "update_value": "0"},
        {"state": "Review", "edit_roles": E, "update_field": "published", "update_value": "0"},
        {"state": "Rework", "update_field": "published", "update_value": "0"},
        {"state": "Published", "update_field": "published", "update_value": "1"},
    ],
    "transitions": [
        {"from_state": "Draft", "to_state": "Review", "action": "Send", "allowed_roles": W,
         "notify": "next", "notify_email": True},
        {"from_state": "Draft", "to_state": "Published", "action": "Publish", "allowed_roles": E},
        {"from_state": "Review", "to_state": "Published", "action": "Publish", "allowed_roles": E,
         "notify": "previous"},
        {"from_state": "Review", "to_state": "Rework", "action": "Return", "allowed_roles": E,
         "require_comment": True, "notify": "previous"},
        {"from_state": "Rework", "to_state": "Review", "action": "Send", "allowed_roles": W,
         "notify": "next"},
        {"from_state": "Published", "to_state": "Review", "action": "Edited", "allowed_roles": W,
         "on_edit": True, "notify": "next"},
    ],
}  # fmt: skip


@pytest_asyncio.fixture
async def article(ctx, db_session):
    from grunt.api.v1.meta import save_doctype
    from grunt.workflow.registry import clear_cache

    await save_doctype(doctype_data={**ARTICLE, "__is_new": True})
    for role in (W, E):
        await ctx.new_doc("Role", {"role_name": role})
    for email, role in ((AUTHOR, W), (REVIEWER, E), (READER, None)):
        roles = [{"role_name": role}] if role else []
        user = {"email": email, "first_name": "T", "last_name": email, "roles": roles}
        if email == REVIEWER:
            user["name"] = REVIEWER_ID
        await ctx.new_doc("User", user)
    clear_cache()
    await ctx.new_doc("Workflow", WORKFLOW)
    await db_session.commit()


def _as(email: str, *roles: str):
    from tests.support import make_user

    return make_user(email, roles=list(roles))


async def _inbox(email: str) -> list[str]:
    rows = await grunt.db.get_all("Notification", filters={"user": email}, fields=["subject"])
    return sorted(r["subject"] for r in rows)


async def _state(name: str) -> tuple[str, int]:
    row = await grunt.db.get_all("Article", filters={"name": name}, fields=["status", "published"])
    return row[0]["status"], int(row[0]["published"] or 0)


async def _buttons(name: str) -> set[str]:
    from grunt.document.base import Document

    return {t["action"] for t in await Document.get_workflow_transitions("Article", name)}


@pytest.mark.asyncio
async def test_review_cycle(article, db_session, engine):
    async with grunt.context(db_session, engine, _as(AUTHOR, W)):
        doc = await grunt.new_doc("Article", {"title": "Report"})
        name = doc["name"]
        assert await _buttons(name) == {"Send"}  # no Publish, no on_edit "Edited"
        await grunt.submit("Article", name, "Send")
    assert await _state(name) == ("Review", 0)
    assert await _inbox(REVIEWER) == ["Send: Report"]
    assert await _inbox(READER) == []

    async with grunt.context(db_session, engine, _as(AUTHOR, W)):
        with pytest.raises(HTTPException) as exc:  # Review: only editors edit
            await grunt.save_doc("Article", name, {"title": "Other"})
        assert exc.value.status_code == 403

    async with grunt.context(db_session, engine, _as(REVIEWER, E)):
        with pytest.raises(HTTPException):
            await grunt.submit("Article", name, "Return")  # comment required
        await grunt.submit("Article", name, "Return", {"__comment": "Add a table"})
    assert await _state(name) == ("Rework", 0)
    assert await _inbox(AUTHOR) == ["Return: Report"]
    comments = await grunt.db.get_all(
        "Comment", filters={"reference_id": name}, fields=["content", "owner"]
    )
    assert len(comments) == 1 and "Add a table" in comments[0]["content"]
    assert comments[0]["owner"] == REVIEWER

    async with grunt.context(db_session, engine, _as(AUTHOR, W)):
        await grunt.save_doc("Article", name, {"title": "Report 2025"})
        await grunt.submit("Article", name, "Send")
    async with grunt.context(db_session, engine, _as(REVIEWER, E)):
        await grunt.save_doc("Article", name, {"title": "Report for 2025"})
        await grunt.submit("Article", name, "Publish")
    assert await _state(name) == ("Published", 1)
    assert "Publish: Report for 2025" in await _inbox(AUTHOR)

    logged = await grunt.db.get_all(
        "ActivityLog", filters={"doc_id": name, "action": "Workflow"}, fields=["user"]
    )
    assert len(logged) == 4


@pytest.mark.asyncio
async def test_state_moves_only_by_transitions(article, db_session, engine):
    async with grunt.context(db_session, engine, _as(AUTHOR, W)):
        with pytest.raises(HTTPException):
            await grunt.new_doc("Article", {"title": "x", "status": "Published"})
        doc = await grunt.new_doc("Article", {"title": "y"})
        assert doc["status"] == "Draft"
        with pytest.raises(HTTPException):
            await grunt.save_doc("Article", doc["name"], {"status": "Published"})
        with pytest.raises(HTTPException):
            await grunt.submit("Article", doc["name"], "Publish")
        # Saving the unchanged state with other fields is a plain edit.
        await grunt.save_doc("Article", doc["name"], {"status": "Draft", "title": "z"})
    # The system user (imports, fixtures) is exempt.
    await grunt.save_doc("Article", doc["name"], {"status": "Published"})
    assert (await _state(doc["name"]))[0] == "Published"


@pytest.mark.asyncio
async def test_edit_of_published_goes_back_to_review(article, db_session, engine):
    async with grunt.context(db_session, engine, _as(REVIEWER, E)):
        doc = await grunt.new_doc("Article", {"title": "Live"})
        await grunt.submit("Article", doc["name"], "Publish")
        await grunt.save_doc("Article", doc["name"], {"title": "Live, fixed"})  # editor: plain edit
    assert await _state(doc["name"]) == ("Published", 1)

    async with grunt.context(db_session, engine, _as(AUTHOR, W)):
        # The form sends the whole document back - unchanged values don't count.
        same = await grunt.get_doc("Article", doc["name"])
        await grunt.save_doc("Article", doc["name"], {k: same[k] for k in ("title", "status")})
        assert await _state(doc["name"]) == ("Published", 1)
        with pytest.raises(HTTPException):  # edits go to review - so does removal
            await grunt.delete_doc("Article", doc["name"])
        await grunt.save_doc("Article", doc["name"], {"title": "Live, rewritten"})
    assert await _state(doc["name"]) == ("Review", 0)
    assert await _inbox(REVIEWER) == ["Edited: Live, rewritten"]


@pytest.mark.asyncio
async def test_controller_sees_current_transition(article, db_session, engine):
    from grunt.hooks import on_doc
    from grunt.workflow.engine import current_transition

    seen: list[tuple[str | None, str]] = []

    @on_doc("Article", "before_save")
    async def _spy(**kwargs):
        if t := current_transition():
            seen.append((t.from_state, t.to_state))

    try:
        async with grunt.context(db_session, engine, _as(AUTHOR, W)):
            doc = await grunt.new_doc("Article", {"title": "t"})
            await grunt.submit("Article", doc["name"], "Send")
    finally:
        from grunt.hooks import DOC_EVENT_REGISTRY

        DOC_EVENT_REGISTRY["Article"]["before_save"].clear()
    assert seen == [("Draft", "Review")]
