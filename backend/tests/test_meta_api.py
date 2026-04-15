"""Tests for the Meta API — DocType CRUD and sync (migrated to whitelisted methods)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

SAMPLE_DOCTYPE = {
    "name": "Task",
    "label": "Завдання",
    "module": "core",
    "fields": [
        {
            "fieldname": "title",
            "label": "Назва",
            "fieldtype": "Text",
            "required": True,
            "in_list_view": True,
        },
        {
            "fieldname": "status",
            "label": "Статус",
            "fieldtype": "Select",
            "options": "Draft\nActive\nDone",
            "default": "Draft",
        },
        {"fieldname": "priority", "label": "Пріоритет", "fieldtype": "Int"},
    ],
}

# ── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_doctype(client: AsyncClient, auth_headers: dict):
    """POST /method/save_doctype → 200."""
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.meta.save_doctype",
        json={"doctype_data": SAMPLE_DOCTYPE},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Task"
    assert data["module"] == "core"
    assert len(data["fields"]) == 3

@pytest.mark.asyncio
async def test_list_doctypes(client: AsyncClient, auth_headers: dict):
    """GET /method/list_doctypes → contains created DocType."""
    await client.post("/api/v1/method/grunt.api.v1.meta.save_doctype", json={"doctype_data": SAMPLE_DOCTYPE}, headers=auth_headers)
    resp = await client.get("/api/v1/method/grunt.api.v1.meta.list_doctypes", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert any(item["name"] == "Task" for item in items)

@pytest.mark.asyncio
async def test_get_one_doctype(client: AsyncClient, auth_headers: dict):
    """GET /method/get_doctype?name=Task → returns correct fields."""
    await client.post("/api/v1/method/grunt.api.v1.meta.save_doctype", json={"doctype_data": SAMPLE_DOCTYPE}, headers=auth_headers)
    resp = await client.get("/api/v1/method/grunt.api.v1.meta.get_doctype", params={"name": "Task"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Task"
    assert data["label"] == "Завдання"
    field_names = [f["fieldname"] for f in data["fields"]]
    assert "title" in field_names
    assert "status" in field_names

@pytest.mark.asyncio
async def test_update_doctype(client: AsyncClient, auth_headers: dict):
    """POST /method/save_doctype (update) → 200."""
    await client.post("/api/v1/method/grunt.api.v1.meta.save_doctype", json={"doctype_data": SAMPLE_DOCTYPE}, headers=auth_headers)

    updated = {
        **SAMPLE_DOCTYPE,
        "fields": SAMPLE_DOCTYPE["fields"]
        + [
            {"fieldname": "deadline", "label": "Дедлайн", "fieldtype": "Date"},
        ],
    }
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.meta.save_doctype",
        json={"doctype_data": updated},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["fields"]) == 4

@pytest.mark.asyncio
async def test_delete_doctype(client: AsyncClient, auth_headers: dict):
    """DELETE via /method/delete_doctype → 200, then GET → 404."""
    await client.post("/api/v1/method/grunt.api.v1.meta.save_doctype", json={"doctype_data": SAMPLE_DOCTYPE}, headers=auth_headers)
    resp = await client.get("/api/v1/method/grunt.api.v1.meta.delete_doctype", params={"name": "Task"}, headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/method/grunt.api.v1.meta.get_doctype", params={"name": "Task"}, headers=auth_headers)
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_sync_doctype(client: AsyncClient, auth_headers: dict):
    """POST /method/sync_doctype → 200."""
    await client.post("/api/v1/method/grunt.api.v1.meta.save_doctype", json={"doctype_data": SAMPLE_DOCTYPE}, headers=auth_headers)
    resp = await client.post("/api/v1/method/grunt.api.v1.meta.sync_doctype", params={"name": "Task"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Task"
    assert "table_name" in data

@pytest.mark.asyncio
async def test_duplicate_doctype_409(client: AsyncClient, auth_headers: dict):
    """Creating a duplicate DocType → 409."""
    await client.post("/api/v1/method/grunt.api.v1.meta.save_doctype", json={"doctype_data": SAMPLE_DOCTYPE}, headers=auth_headers)
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.meta.save_doctype", 
        json={"doctype_data": {**SAMPLE_DOCTYPE, "__is_new": True}}, 
        headers=auth_headers
    )
    assert resp.status_code == 409
