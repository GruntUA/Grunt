"""Tests for the Workflow engine — state machine transitions."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ── Helpers ───────────────────────────────────────────────────────────────

DOCTYPE_PAYLOAD = {
    "name": "Contract",
    "label": "Договір",
    "module": "crm",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Text"},
    ],
    "workflow": {
        "state_field": "status",
        "states": [
            {"name": "Draft", "label": "Чернетка", "is_initial": True},
            {"name": "Submitted", "label": "Надіслано"},
            {"name": "Approved", "label": "Погоджено", "is_final": True},
            {"name": "Rejected", "label": "Відхилено", "is_final": True},
        ],
        "transitions": [
            {"action": "Submit", "from_state": "Draft", "to_state": "Submitted", "allowed_roles": []},
            {"action": "Approve", "from_state": "Submitted", "to_state": "Approved", "allowed_roles": []},
            {"action": "Reject", "from_state": "Submitted", "to_state": "Rejected", "allowed_roles": []},
        ],
    },
}


@pytest.mark.asyncio
async def test_create_doctype_with_workflow(client: AsyncClient, auth_headers: dict):
    """DocType with workflow can be created."""
    resp = await client.post(
        "/api/v1/meta/doctypes",
        json=DOCTYPE_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["workflow"]["state_field"] == "status"
    assert len(data["workflow"]["states"]) == 4


@pytest.mark.asyncio
async def test_workflow_transitions_empty_for_no_workflow(client: AsyncClient, auth_headers: dict):
    """A DocType without workflow returns empty transitions list."""
    # Create a simple doctype without workflow
    resp = await client.post(
        "/api/v1/meta/doctypes",
        json={"name": "Note", "label": "Нотатка", "module": "core", "fields": []},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Create a document
    resp = await client.post(
        "/api/v1/docs/Note",
        json={"title": "Test Note"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["data"]["id"]

    # Check transitions
    resp = await client.get(f"/api/v1/docs/Note/{doc_id}/transitions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_workflow_initial_transitions(client: AsyncClient, auth_headers: dict):
    """A doc in Draft state shows Submit transition."""
    # Create doctype
    await client.post("/api/v1/meta/doctypes", json=DOCTYPE_PAYLOAD, headers=auth_headers)

    # Create doc (status will be None initially — no initial state forced)
    resp = await client.post(
        "/api/v1/docs/Contract",
        json={"title": "Test Contract", "status": "Draft"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["data"]["id"]

    # Get transitions
    resp = await client.get(f"/api/v1/docs/Contract/{doc_id}/transitions", headers=auth_headers)
    assert resp.status_code == 200
    transitions = resp.json()["data"]
    assert any(t["action"] == "Submit" for t in transitions)


@pytest.mark.asyncio
async def test_workflow_apply_transition(client: AsyncClient, auth_headers: dict):
    """Applying a transition changes the document state."""
    await client.post("/api/v1/meta/doctypes", json=DOCTYPE_PAYLOAD, headers=auth_headers)

    resp = await client.post(
        "/api/v1/docs/Contract",
        json={"title": "Test Contract", "status": "Draft"},
        headers=auth_headers,
    )
    doc_id = resp.json()["data"]["id"]

    # Apply Submit transition
    resp = await client.post(
        f"/api/v1/docs/Contract/{doc_id}/transition",
        json={"action": "Submit"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    updated = resp.json()["data"]
    assert updated["status"] == "Submitted"


@pytest.mark.asyncio
async def test_workflow_invalid_transition_rejected(client: AsyncClient, auth_headers: dict):
    """Applying a non-available transition returns 400."""
    await client.post("/api/v1/meta/doctypes", json=DOCTYPE_PAYLOAD, headers=auth_headers)

    resp = await client.post(
        "/api/v1/docs/Contract",
        json={"title": "Test", "status": "Draft"},
        headers=auth_headers,
    )
    doc_id = resp.json()["data"]["id"]

    # Try to apply Approve from Draft (invalid)
    resp = await client.post(
        f"/api/v1/docs/Contract/{doc_id}/transition",
        json={"action": "Approve"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_workflow_multi_step(client: AsyncClient, auth_headers: dict):
    """Full workflow: Draft → Submitted → Approved."""
    await client.post("/api/v1/meta/doctypes", json=DOCTYPE_PAYLOAD, headers=auth_headers)

    resp = await client.post(
        "/api/v1/docs/Contract",
        json={"title": "Multi-step", "status": "Draft"},
        headers=auth_headers,
    )
    doc_id = resp.json()["data"]["id"]

    # Submit
    resp = await client.post(
        f"/api/v1/docs/Contract/{doc_id}/transition",
        json={"action": "Submit"},
        headers=auth_headers,
    )
    assert resp.json()["data"]["status"] == "Submitted"

    # Approve
    resp = await client.post(
        f"/api/v1/docs/Contract/{doc_id}/transition",
        json={"action": "Approve"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "Approved"
