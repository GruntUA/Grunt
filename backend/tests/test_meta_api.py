"""Tests for the Meta API — DocType CRUD and sync."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


SAMPLE_DOCTYPE = {
    "name": "Task",
    "label": "Завдання",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Text", "required": True, "in_list_view": True},
        {"fieldname": "status", "label": "Статус", "fieldtype": "Select", "options": "Draft\nActive\nDone", "default": "Draft"},
        {"fieldname": "priority", "label": "Пріоритет", "fieldtype": "Int"},
    ],
}


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_doctype(client: AsyncClient, auth_headers: dict):
    """POST /meta/doctypes → 201."""
    resp = await client.post(
        "/api/v1/meta/doctypes",
        json=SAMPLE_DOCTYPE,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "Task"
    assert data["module"] == "core"
    assert len(data["fields"]) == 3


@pytest.mark.asyncio
async def test_list_doctypes(client: AsyncClient, auth_headers: dict):
    """GET /meta/doctypes → contains created DocType."""
    await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)
    resp = await client.get("/api/v1/meta/doctypes", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert any(item["name"] == "Task" for item in items)


@pytest.mark.asyncio
async def test_get_one_doctype(client: AsyncClient, auth_headers: dict):
    """GET /meta/doctypes/{name} → returns correct fields."""
    await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)
    resp = await client.get("/api/v1/meta/doctypes/Task", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Task"
    assert data["label"] == "Завдання"
    field_names = [f["fieldname"] for f in data["fields"]]
    assert "title" in field_names
    assert "status" in field_names


@pytest.mark.asyncio
async def test_update_doctype(client: AsyncClient, auth_headers: dict):
    """PUT /meta/doctypes/{name} → 200, table updated."""
    await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)

    updated = {**SAMPLE_DOCTYPE, "fields": SAMPLE_DOCTYPE["fields"] + [
        {"fieldname": "deadline", "label": "Дедлайн", "fieldtype": "Date"},
    ]}
    resp = await client.put(
        "/api/v1/meta/doctypes/Task",
        json=updated,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["fields"]) == 4


@pytest.mark.asyncio
async def test_delete_doctype(client: AsyncClient, auth_headers: dict):
    """DELETE → 200, then GET → 404."""
    await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)
    resp = await client.delete("/api/v1/meta/doctypes/Task", headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/meta/doctypes/Task", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_doctype(client: AsyncClient, auth_headers: dict):
    """POST /meta/doctypes/{name}/sync → 200."""
    await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)
    resp = await client.post("/api/v1/meta/doctypes/Task/sync", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Task"
    assert "table_name" in data


@pytest.mark.asyncio
async def test_duplicate_doctype_409(client: AsyncClient, auth_headers: dict):
    """Creating a duplicate DocType → 409."""
    await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)
    resp = await client.post("/api/v1/meta/doctypes", json=SAMPLE_DOCTYPE, headers=auth_headers)
    assert resp.status_code == 409
