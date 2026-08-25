"""Tests for the Workflow engine — state machine transitions.

Workflow is a regular DocType (grunt/metadata/doctypes/Workflow): its
documents reference the DocType they govern via `document_type`, instead of
being embedded in that DocType's own definition.
"""

from __future__ import annotations

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────

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

    ``new_doc()`` returns the inserted row as-is — it doesn't re-attach child
    tables (``states``/``transitions``), so callers that need them must re-fetch.
    """
    created = await ctx.new_doc("Workflow", payload)
    await ctx.db._session().commit()
    return await ctx.get_doc("Workflow", created["name"])


@pytest.mark.asyncio
async def test_create_doctype_with_workflow(ctx):
    """A Workflow document can be created for a DocType."""
    from grunt.api.v1.meta import save_doctype

    await save_doctype(DOCTYPE_PAYLOAD)
    await ctx.db._session().commit()

    workflow = await _create_workflow(ctx, CONTRACT_WORKFLOW)
    assert workflow["workflow_state_field"] == "status"
    assert len(workflow["states"]) == 4


@pytest.mark.asyncio
async def test_workflow_transitions_empty_for_no_workflow(ctx):
    """A DocType without a Workflow document returns empty transitions list."""
    from grunt.api.v1.meta import save_doctype
    from grunt.api.v1.workflow import get_transitions

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
    from grunt.api.v1.meta import save_doctype
    from grunt.api.v1.workflow import get_transitions

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
    from grunt.api.v1.meta import save_doctype

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

    from grunt.api.v1.meta import save_doctype

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
        # No allowed_roles — the workflow-level gate alone would let
        # anyone who can read the doc apply this transition.
        {"action": "Submit", "from_state": "Draft", "to_state": "Submitted"},
    ],
}


@pytest.mark.asyncio
async def test_apply_transition_requires_write_permission(ctx, db_session, engine):
    """Regression: apply_transition() used to mutate the document's state via
    the unguarded grunt.db.set_value() — a user with only READ access (and no
    allowed_roles configured on the transition itself) could still push the
    document through its workflow. Now uses the guarded grunt.set_value(),
    which enforces the doctype's own write permission.
    """
    from fastapi import HTTPException

    from grunt.api.v1.meta import save_doctype
    from grunt.app import grunt
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
    """Full workflow: Draft → Submitted → Approved."""
    from grunt.api.v1.meta import save_doctype

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
