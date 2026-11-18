"""Workflow guards (FRAPPE_GAP #19): no approving your own document, a broken
condition closes the transition, "ask for confirmation", the state's message,
and the ``transition`` a Server Script sees on ``on_transition``."""

import pytest

import grunt
from grunt.api.v1.document import workflow as workflow_api
from grunt.api.v1.meta import get_doctype, save_doctype
from grunt.metadata.doctypes.DocType.tests.test_workflow import _create_workflow
from tests.support import make_user

DOCTYPE = {
    "name": "Memo",
    "label": "Memo",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data"},
    ],
    "permissions": [{"role": "MemoApprover", "actions": ["read", "write", "create"]}],
}

WORKFLOW = {
    "document_type": "Memo",
    "workflow_state_field": "status",
    "states": [
        {"state": "Draft", "is_initial": True},
        {"state": "Review", "message": "Awaiting review - editing is locked", "color": "yellow"},
        {"state": "Approved", "is_final": True},
        {"state": "Archived", "is_final": True},
    ],
    "transitions": [
        {"action": "Send", "from_state": "Draft", "to_state": "Review"},
        {
            "action": "Approve",
            "from_state": "Review",
            "to_state": "Approved",
            "allowed_roles": "MemoApprover",
            "deny_self_approval": True,
        },
        {
            "action": "Archive",
            "from_state": "Review",
            "to_state": "Archived",
            "allowed_roles": "MemoApprover",
            "confirm": True,
        },
    ],
}

AUTHOR = make_user("author@grunt.example.com", roles=["MemoApprover"])
OTHER = make_user("other@grunt.example.com", roles=["MemoApprover"])


async def _memo_in_review(ctx, db_session, engine) -> str:
    await save_doctype(doctype_data={**DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()
    await _create_workflow(ctx, WORKFLOW)
    async with grunt.context(db_session, engine, AUTHOR):
        doc = await grunt.new_doc("Memo", {"title": "Mine", "status": "Draft"})
        await grunt.submit("Memo", doc["name"], "Send")
    await ctx.db._session().commit()
    return doc["name"]


async def _actions(db_session, engine, user, doc_id: str) -> dict[str, dict]:
    async with grunt.context(db_session, engine, user):
        return {t["action"]: t for t in await workflow_api.get_workflow_transitions("Memo", doc_id)}


@pytest.mark.asyncio
async def test_author_cannot_approve_own_document(ctx, db_session, engine):
    from fastapi import HTTPException

    doc_id = await _memo_in_review(ctx, db_session, engine)

    mine = await _actions(db_session, engine, AUTHOR, doc_id)
    assert "Approve" not in mine and "Archive" in mine
    async with grunt.context(db_session, engine, AUTHOR):
        with pytest.raises(HTTPException) as excinfo:
            await grunt.submit("Memo", doc_id, "Approve")
    assert excinfo.value.status_code == 400

    assert "Approve" in await _actions(db_session, engine, OTHER, doc_id)
    async with grunt.context(db_session, engine, OTHER):
        updated = await grunt.submit("Memo", doc_id, "Approve")
    assert updated["status"] == "Approved"


@pytest.mark.asyncio
async def test_next_actors_leave_out_the_author(ctx, db_session, engine):
    from grunt.workflow.actors import next_actors

    doc_id = await _memo_in_review(ctx, db_session, engine)
    doc = await ctx.get_doc("Memo", doc_id)
    approve_only = {
        **WORKFLOW,
        "transitions": [t for t in WORKFLOW["transitions"] if t["action"] != "Archive"],
    }
    workflow = await ctx.get_doc("Workflow", (await ctx.db.get_all("Workflow", limit=1))[0]["name"])
    await ctx.save_doc("Workflow", workflow["name"], {"transitions": approve_only["transitions"]})
    await ctx.db._session().commit()

    # Only assigned holders count - grant the role to both users for real.
    for user in (AUTHOR, OTHER):
        await ctx.new_doc(
            "User",
            {
                "email": user.email,
                "first_name": user.email.split("@")[0],
                "last_name": "Test",
                "roles": [{"role_name": "MemoApprover"}],
            },
        )
    await ctx.db._session().commit()

    actors = await next_actors("Memo", doc)
    assert OTHER.email in actors
    assert AUTHOR.email not in actors


@pytest.mark.asyncio
async def test_a_broken_condition_closes_the_transition(ctx, db_session, engine):
    doc_id = await _memo_in_review(ctx, db_session, engine)
    workflow = (await ctx.db.get_all("Workflow", limit=1))[0]["name"]
    broken = [
        {**t, "condition": "doc['no_such_field'] == 1"} if t["action"] == "Archive" else t
        for t in WORKFLOW["transitions"]
    ]
    await ctx.save_doc("Workflow", workflow, {"transitions": broken})
    await ctx.db._session().commit()

    assert "Archive" not in await _actions(db_session, engine, OTHER, doc_id)


@pytest.mark.asyncio
async def test_confirm_and_state_message_reach_the_form(ctx, db_session, engine):
    doc_id = await _memo_in_review(ctx, db_session, engine)

    actions = await _actions(db_session, engine, OTHER, doc_id)
    assert actions["Archive"]["confirm"] is True
    assert actions["Approve"]["confirm"] is False

    meta = await get_doctype("Memo")
    assert meta["workflow_state_messages"] == {
        "Review": {"message": "Awaiting review - editing is locked", "color": "yellow"}
    }
    # The builder edits the source - no derived keys there.
    assert "workflow_state_messages" not in await get_doctype("Memo", raw=True)


@pytest.mark.asyncio
async def test_server_script_sees_the_transition():
    from grunt.core_events import _transition_context
    from grunt.scripting.server_script import ServerScriptRunner

    kwargs = {
        "event": "on_transition",
        "action": "Approve",
        "from_state": "Review",
        "to_state": "Approved",
        "comment": None,
    }
    context = _transition_context(kwargs)
    assert context == {
        "transition": {
            "action": "Approve",
            "from_state": "Review",
            "to_state": "Approved",
            "comment": None,
        }
    }
    assert _transition_context({**kwargs, "event": "after_save"}) is None

    result = await ServerScriptRunner().execute(
        "grunt.response = {'to': transition['to_state'], 'by': transition['action']}",
        extra_context=context,
    )
    assert result.success, result.error
    assert result.response == {"to": "Approved", "by": "Approve"}


def test_rows_from_before_the_new_columns_still_load():
    """`grunt migrate` adds the columns as NULL on existing rows - they load with
    the defaults instead of failing every workflow."""
    from grunt.metadata.doctype import WorkflowState, WorkflowTransition

    state = WorkflowState.model_validate({"state": "Draft", "message": None})
    assert state.message == ""
    transition = WorkflowTransition.model_validate(
        {
            "from_state": "Draft",
            "to_state": "Review",
            "action": "Send",
            "deny_self_approval": None,
            "confirm": None,
        }
    )
    assert transition.deny_self_approval is False and transition.confirm is False


@pytest.mark.asyncio
async def test_a_hidden_owner_does_not_let_the_author_approve(ctx, db_session, engine):
    """The author's read of the document has `owner` masked - the check reads
    the stored owner, not the masked document."""
    hidden = {
        **DOCTYPE,
        "permissions": [
            {
                "role": "MemoApprover",
                "actions": ["read", "write", "create"],
                "hidden_fields": ["owner"],
            }
        ],
    }
    await save_doctype(doctype_data={**hidden, "__is_new": True})
    await ctx.db._session().commit()
    await _create_workflow(ctx, WORKFLOW)
    async with grunt.context(db_session, engine, AUTHOR):
        doc = await grunt.new_doc("Memo", {"title": "Mine", "status": "Draft"})
        await grunt.submit("Memo", doc["name"], "Send")
        seen = await grunt.get_doc("Memo", doc["name"])
    await ctx.db._session().commit()
    assert "owner" not in seen or not seen["owner"]  # the rule really masks it

    assert "Approve" not in await _actions(db_session, engine, AUTHOR, doc["name"])
    assert "Approve" in await _actions(db_session, engine, OTHER, doc["name"])
