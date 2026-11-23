"""Awaiting my action (FRAPPE_GAP #19, step 2): workflow documents a user can
move on now, for the home page's "My work" panel (grunt/workflow/inbox.py)."""

import pytest

import grunt
from grunt.api.v1.meta import save_doctype
from grunt.metadata.doctypes.DocType.tests.test_workflow import _create_workflow
from grunt.workflow.inbox import awaiting_actions
from tests.support import make_user

DOCTYPE = {
    "name": "Request",
    "label": "Request",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
    ],
    "title_field": "title",
    "permissions": [
        {"role": "Requester", "actions": ["read", "write", "create"]},
        {"role": "Reviewer", "actions": ["read", "write"]},
    ],
}

WORKFLOW = {
    "document_type": "Request",
    "workflow_state_field": "status",
    "states": [
        {"state": "Draft", "is_initial": True},
        {"state": "Review", "label": "In review", "color": "yellow"},
        {"state": "Done", "is_final": True},
    ],
    "transitions": [
        {
            "action": "Send",
            "from_state": "Draft",
            "to_state": "Review",
            "allowed_roles": "Requester",
        },
        {
            "action": "Approve",
            "from_state": "Review",
            "to_state": "Done",
            "allowed_roles": "Reviewer",
            "deny_self_approval": True,
        },
        {
            "action": "Send back",
            "from_state": "Review",
            "to_state": "Draft",
            "allowed_roles": "Reviewer",
        },
    ],
}

REQUESTER = make_user("requester@grunt.example.com", roles=["Requester", "Reviewer"])
REVIEWER = make_user("reviewer@grunt.example.com", roles=["Reviewer"])
ADMIN = make_user("admin2@grunt.example.com", is_superadmin=True)


async def _setup(ctx, db_session, engine) -> str:
    await save_doctype(doctype_data={**DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()
    await _create_workflow(ctx, WORKFLOW)
    # role_holders reads the assignments - the users exist for real.
    for user, roles in (
        (REQUESTER, ["Requester", "Reviewer"]),
        (REVIEWER, ["Reviewer"]),
        (ADMIN, ["System Manager"]),
    ):
        await ctx.new_doc(
            "User",
            {
                "email": user.email,
                "first_name": user.email.split("@")[0],
                "last_name": "Test",
                "roles": [{"role_name": r} for r in roles],
            },
        )
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, REQUESTER):
        doc = await grunt.new_doc("Request", {"title": "New laptop", "status": "Draft"})
        await grunt.new_doc("Request", {"title": "Still a draft", "status": "Draft"})
    await ctx.db._session().commit()
    async with grunt.context(db_session, engine, REQUESTER):
        await grunt.submit("Request", doc.name, "Send")
    await ctx.db._session().commit()
    return doc.name


async def _awaiting(db_session, engine, user) -> list[dict]:
    async with grunt.context(db_session, engine, user):
        return await awaiting_actions(user.email)


@pytest.mark.asyncio
async def test_reviewer_sees_the_document_in_review(ctx, db_session, engine):
    doc_id = await _setup(ctx, db_session, engine)

    items = await _awaiting(db_session, engine, REVIEWER)
    assert [(i["name"], i["title"]) for i in items] == [(doc_id, "New laptop")]
    item = items[0]
    assert item["doctype"] == "Request"
    assert item["state"] == "Review" and item["state_label"] == "In review"
    assert item["color"] == "yellow"
    assert item["actions"] == ["Approve", "Send back"]


@pytest.mark.asyncio
async def test_author_is_not_awaited_on_their_own_approval(ctx, db_session, engine):
    doc_id = await _setup(ctx, db_session, engine)

    items = {i["name"]: i for i in await _awaiting(db_session, engine, REQUESTER)}
    # Their own request in review: "Send back" yes, "Approve" no (deny_self_approval).
    assert items[doc_id]["actions"] == ["Send back"]
    # Their drafts await "Send".
    drafts = [i for i in items.values() if i["state"] == "Draft"]
    assert len(drafts) == 1 and drafts[0]["actions"] == ["Send"]


@pytest.mark.asyncio
async def test_system_manager_without_the_role_is_not_flooded(ctx, db_session, engine):
    await _setup(ctx, db_session, engine)
    assert await _awaiting(db_session, engine, ADMIN) == []


@pytest.mark.asyncio
async def test_my_work_carries_the_awaiting_documents(ctx, db_session, engine):
    from grunt.api.v1.workspace import get_my_work

    doc_id = await _setup(ctx, db_session, engine)
    async with grunt.context(db_session, engine, REVIEWER):
        work = await get_my_work()
    assert [a["name"] for a in work["awaiting"]] == [doc_id]
    assert work["counts"]["awaiting"] == 1
