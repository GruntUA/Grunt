"""Tests for the Workflow engine - state machine transitions.

Workflow is a regular DocType (grunt/metadata/doctypes/Workflow): its
documents reference the DocType they govern via `document_type`, instead of
being embedded in that DocType's own definition.
"""

from __future__ import annotations

import pytest

import grunt
from grunt.api.v1.meta import save_doctype
from grunt.api.v1.workflow import get_transitions

# Helpers

DOCTYPE_PAYLOAD = {
    "name": "Contract",
    "label": "Договір",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Text"},
        {"fieldname": "status", "label": "Статус", "fieldtype": "Text"},
    ],
}

CONTRACT_WORKFLOW = {
    "document_type": "Contract",
    "workflow_state_field": "status",
    "states": [
        {"state": "Draft", "label": "Чернетка", "is_initial": True},
        {"state": "Submitted", "label": "Надіслано"},
        {"state": "Approved", "label": "Погоджено", "is_final": True},
        {"state": "Rejected", "label": "Відхилено", "is_final": True},
    ],
    "transitions": [
        {"action": "Submit", "from_state": "Draft", "to_state": "Submitted"},
        {"action": "Approve", "from_state": "Submitted", "to_state": "Approved"},
        {"action": "Reject", "from_state": "Submitted", "to_state": "Rejected"},
    ],
}


async def _create_workflow(ctx, payload: dict) -> dict:
    """Create a Workflow document, flush, and re-read it with its child rows.

    ``new_doc()`` returns the inserted row as-is - it doesn't re-attach child
    tables (``states``/``transitions``), so callers that need them must re-fetch.
    """
    created = await ctx.new_doc("Workflow", payload)
    await ctx.db._session().commit()
    return await ctx.get_doc("Workflow", created["name"])


@pytest.mark.asyncio
async def test_create_doctype_with_workflow(ctx):
    """A Workflow document can be created for a DocType."""
    await save_doctype(DOCTYPE_PAYLOAD)
    await ctx.db._session().commit()

    workflow = await _create_workflow(ctx, CONTRACT_WORKFLOW)
    assert workflow["workflow_state_field"] == "status"
    assert len(workflow["states"]) == 4


@pytest.mark.asyncio
async def test_workflow_transitions_empty_for_no_workflow(ctx):
    """A DocType without a Workflow document returns empty transitions list."""
    # Create a simple doctype without workflow
    await save_doctype({"name": "Note", "label": "Нотатка", "module": "core", "fields": []})
    await ctx.db._session().commit()

    # Create a document
    doc = await ctx.new_doc("Note", {"title": "Test Note"})
    doc_id = doc["name"]

    # Check transitions
    transitions = await get_transitions("Note", doc_id)
    assert transitions == []


@pytest.mark.asyncio
async def test_workflow_initial_transitions(ctx):
    """A doc in Draft state shows Submit transition."""
    # Create doctype + workflow
    await save_doctype(DOCTYPE_PAYLOAD)
    await ctx.db._session().commit()
    await _create_workflow(ctx, CONTRACT_WORKFLOW)

    # Create doc
    doc = await ctx.new_doc("Contract", {"title": "Test Contract", "status": "Draft"})
    doc_id = doc["name"]

    # Get transitions
    transitions = await get_transitions("Contract", doc_id)
    assert any(t["action"] == "Submit" for t in transitions)


@pytest.mark.asyncio
async def test_workflow_apply_transition(ctx):
    """Applying a transition changes the document state."""
    await save_doctype(DOCTYPE_PAYLOAD)
    await ctx.db._session().commit()
    await _create_workflow(ctx, CONTRACT_WORKFLOW)

    doc = await ctx.new_doc("Contract", {"title": "Test Contract", "status": "Draft"})
    doc_id = doc["name"]

    # Apply Submit transition
    updated = await ctx.submit("Contract", doc_id, "Submit")
    assert updated["status"] == "Submitted"


@pytest.mark.asyncio
async def test_workflow_invalid_transition_rejected(ctx):
    """Applying a non-available transition returns 409 (Conflict)."""
    from fastapi import HTTPException

    await save_doctype(DOCTYPE_PAYLOAD)
    await ctx.db._session().commit()
    await _create_workflow(ctx, CONTRACT_WORKFLOW)

    doc = await ctx.new_doc("Contract", {"title": "Test", "status": "Draft"})
    doc_id = doc["name"]

    # Try to apply Approve from Draft (invalid)
    with pytest.raises(HTTPException) as excinfo:
        await ctx.submit("Contract", doc_id, "Approve")
    assert excinfo.value.status_code == 400


GUARDED_WORKFLOW_DOCTYPE = {
    "name": "GuardedContract",
    "label": "Guarded Contract",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Text"},
        {"fieldname": "status", "label": "Статус", "fieldtype": "Text"},
    ],
    "permissions": [
        {"role": "ContractReader", "read": True},
        {"role": "ContractApprover", "read": True, "write": True},
    ],
}

GUARDED_CONTRACT_WORKFLOW = {
    "document_type": "GuardedContract",
    "workflow_state_field": "status",
    "states": [
        {"state": "Draft", "label": "Чернетка", "is_initial": True},
        {"state": "Submitted", "label": "Надіслано"},
    ],
    "transitions": [
        # No allowed_roles - the workflow-level gate alone would let
        # anyone who can read the doc apply this transition.
        {"action": "Submit", "from_state": "Draft", "to_state": "Submitted"},
    ],
}


@pytest.mark.asyncio
async def test_apply_transition_requires_write_permission(ctx, db_session, engine):
    """Regression: apply_transition() used to mutate the document's state via
    the unguarded grunt.db.set_value() - a user with only READ access (and no
    allowed_roles configured on the transition itself) could still push the
    document through its workflow. Now uses the guarded grunt.set_value(),
    which enforces the doctype's own write permission.
    """
    from fastapi import HTTPException

    from tests.support import make_user

    await save_doctype(doctype_data={**GUARDED_WORKFLOW_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()
    await _create_workflow(ctx, GUARDED_CONTRACT_WORKFLOW)

    doc = await ctx.new_doc("GuardedContract", {"title": "Test", "status": "Draft"})
    doc_id = doc["name"]
    await ctx.db._session().commit()

    reader = make_user("reader@grunt.example.com", roles=["ContractReader"])
    async with grunt.context(db_session, engine, reader):
        with pytest.raises(HTTPException) as excinfo:
            await grunt.submit("GuardedContract", doc_id, "Submit")
    assert excinfo.value.status_code == 403

    approver = make_user("approver@grunt.example.com", roles=["ContractApprover"])
    async with grunt.context(db_session, engine, approver):
        updated = await grunt.submit("GuardedContract", doc_id, "Submit")
    assert updated["status"] == "Submitted"


@pytest.mark.asyncio
async def test_workflow_multi_step(ctx):
    """Full workflow: Draft -> Submitted -> Approved."""
    await save_doctype(DOCTYPE_PAYLOAD)
    await ctx.db._session().commit()
    await _create_workflow(ctx, CONTRACT_WORKFLOW)

    doc = await ctx.new_doc("Contract", {"title": "Multi-step", "status": "Draft"})
    doc_id = doc["name"]

    # Submit
    updated = await ctx.submit("Contract", doc_id, "Submit")
    assert updated["status"] == "Submitted"

    # Approve
    updated = await ctx.submit("Contract", doc_id, "Approve")
    assert updated["status"] == "Approved"


PROMPT_FIELD_DOCTYPE = {
    "name": "TaskTicket",
    "label": "Task ticket",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Text"},
        {"fieldname": "status", "label": "Статус", "fieldtype": "Text"},
        {"fieldname": "resolution_note", "label": "Виконані роботи", "fieldtype": "LongText"},
    ],
}

PROMPT_FIELD_WORKFLOW = {
    "document_type": "TaskTicket",
    "workflow_state_field": "status",
    "states": [
        {"state": "Open", "label": "Відкрито", "is_initial": True},
        {"state": "Done", "label": "Виконано"},
    ],
    "transitions": [
        {
            "action": "Виконати",
            "from_state": "Open",
            "to_state": "Done",
            "condition": "doc['resolution_note'] != None and doc['resolution_note'] != ''",
            "prompt_fields": "resolution_note",
        },
    ],
}


@pytest.mark.asyncio
async def test_workflow_prompt_fields_shown_before_values_filled(ctx):
    """A transition with prompt_fields stays available even before its
    condition field has a value - the dialog is what collects it."""
    await save_doctype(PROMPT_FIELD_DOCTYPE)
    await ctx.db._session().commit()
    await _create_workflow(ctx, PROMPT_FIELD_WORKFLOW)

    doc = await ctx.new_doc("TaskTicket", {"title": "Test", "status": "Open"})
    doc_id = doc["name"]

    transitions = await get_transitions("TaskTicket", doc_id)
    assert len(transitions) == 1
    assert transitions[0]["prompt_fields"] == ["resolution_note"]


@pytest.mark.asyncio
async def test_workflow_prompt_fields_rejects_empty_values(ctx):
    """Applying a prompt_fields transition without the required value fails."""
    from fastapi import HTTPException

    await save_doctype(PROMPT_FIELD_DOCTYPE)
    await ctx.db._session().commit()
    await _create_workflow(ctx, PROMPT_FIELD_WORKFLOW)

    doc = await ctx.new_doc("TaskTicket", {"title": "Test", "status": "Open"})
    doc_id = doc["name"]

    with pytest.raises(HTTPException) as excinfo:
        await ctx.submit("TaskTicket", doc_id, "Виконати")
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_workflow_prompt_fields_applies_dialog_values(ctx):
    """Applying a prompt_fields transition writes the dialog values and the
    new state in the same update - only fields listed in prompt_fields."""
    await save_doctype(PROMPT_FIELD_DOCTYPE)
    await ctx.db._session().commit()
    await _create_workflow(ctx, PROMPT_FIELD_WORKFLOW)

    doc = await ctx.new_doc("TaskTicket", {"title": "Test", "status": "Open"})
    doc_id = doc["name"]

    updated = await ctx.submit(
        "TaskTicket",
        doc_id,
        "Виконати",
        {"resolution_note": "Полагодив принтер", "title": "Should be ignored"},
    )
    assert updated["status"] == "Done"
    assert updated["resolution_note"] == "Полагодив принтер"
    assert updated["title"] == "Test"
