"""Tests for the Document API — dynamic CRUD for DocType instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

TEST_DOCTYPE = {
    "name": "TestItem",
    "label": "Test Item",
    "module": "core",
    "fields": [
        {
            "fieldname": "title",
            "label": "Title",
            "fieldtype": "Text",
            "required": True,
            "in_list_view": True,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Draft\nActive\nArchived",
            "default": "Draft",
        },
        {"fieldname": "count", "label": "Count", "fieldtype": "Int"},
        {"fieldname": "description", "label": "Description", "fieldtype": "LongText"},
    ],
    "search_fields": ["title"],
}


@pytest.fixture
async def setup_doctype(client: AsyncClient, auth_headers: dict):
    """Create the TestItem DocType before document tests."""
    resp = await client.post("/api/v1/meta/doctypes", json=TEST_DOCTYPE, headers=auth_headers)
    assert resp.status_code == 201


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """POST /docs/TestItem → 201 with id/name/owner/created_at."""
    resp = await client.post(
        "/api/v1/docs/TestItem",
        json={"title": "My First Item", "status": "Draft"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["id"]
    assert data["name"]
    assert data["owner"] == "admin@grunt.example.com"
    assert data["created_at"]
    assert data["title"] == "My First Item"


@pytest.mark.asyncio
async def test_create_without_required_field(
    client: AsyncClient, auth_headers: dict, setup_doctype
):
    """POST without required field → 422."""
    resp = await client.post(
        "/api/v1/docs/TestItem",
        json={"status": "Draft"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET /docs/TestItem → returns created documents."""
    await client.post("/api/v1/docs/TestItem", json={"title": "Item A"}, headers=auth_headers)
    await client.post("/api/v1/docs/TestItem", json={"title": "Item B"}, headers=auth_headers)
    resp = await client.get("/api/v1/docs/TestItem", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 2


@pytest.mark.asyncio
async def test_list_filter_by_status(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET /docs/TestItem?filter[status]=Draft → only Draft."""
    await client.post(
        "/api/v1/docs/TestItem", json={"title": "A", "status": "Draft"}, headers=auth_headers
    )
    await client.post(
        "/api/v1/docs/TestItem", json={"title": "B", "status": "Active"}, headers=auth_headers
    )

    resp = await client.get("/api/v1/docs/TestItem?filter[status]=Draft", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "Draft"


@pytest.mark.asyncio
async def test_list_search(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET /docs/TestItem?search=Alpha → searches by title (search_fields)."""
    await client.post("/api/v1/docs/TestItem", json={"title": "Alpha Item"}, headers=auth_headers)
    await client.post("/api/v1/docs/TestItem", json={"title": "Beta Item"}, headers=auth_headers)

    resp = await client.get("/api/v1/docs/TestItem?search=Alpha", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert "Alpha" in data[0]["title"]


@pytest.mark.asyncio
async def test_list_pagination(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET ?page=2&per_page=2 → correct pagination meta."""
    for i in range(5):
        await client.post(
            "/api/v1/docs/TestItem", json={"title": f"Item {i}"}, headers=auth_headers
        )

    resp = await client.get("/api/v1/docs/TestItem?page=2&per_page=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 5
    assert body["meta"]["page"] == 2
    assert body["meta"]["per_page"] == 2
    assert body["meta"]["pages"] == 3
    assert len(body["data"]) == 2


@pytest.mark.asyncio
async def test_get_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET /docs/TestItem/{id} → returns the document."""
    create_resp = await client.post(
        "/api/v1/docs/TestItem",
        json={"title": "Single Item"},
        headers=auth_headers,
    )
    doc_id = create_resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/docs/TestItem/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Single Item"


@pytest.mark.asyncio
async def test_get_nonexistent_404(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET nonexistent document → 404."""
    resp = await client.get("/api/v1/docs/TestItem/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """PUT update → modified_at changed."""
    create_resp = await client.post(
        "/api/v1/docs/TestItem",
        json={"title": "Original"},
        headers=auth_headers,
    )
    doc = create_resp.json()["data"]

    resp = await client.put(
        f"/api/v1/docs/TestItem/{doc['id']}",
        json={"title": "Updated"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    updated = resp.json()["data"]
    assert updated["title"] == "Updated"
    assert updated["modified_at"] != doc["modified_at"]


@pytest.mark.asyncio
async def test_update_owner_ignored(client: AsyncClient, auth_headers: dict, setup_doctype):
    """PUT trying to change owner → ignored."""
    create_resp = await client.post(
        "/api/v1/docs/TestItem",
        json={"title": "Test"},
        headers=auth_headers,
    )
    doc = create_resp.json()["data"]

    resp = await client.put(
        f"/api/v1/docs/TestItem/{doc['id']}",
        json={"owner": "hacker@evil.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["owner"] == "admin@grunt.example.com"


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """DELETE → 200, then GET → 404."""
    create_resp = await client.post(
        "/api/v1/docs/TestItem",
        json={"title": "ToDelete"},
        headers=auth_headers,
    )
    doc_id = create_resp.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/docs/TestItem/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/docs/TestItem/{doc_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_partial_fields(client: AsyncClient, auth_headers: dict, setup_doctype):
    """GET ?fields=id,title → other fields absent."""
    await client.post(
        "/api/v1/docs/TestItem",
        json={"title": "Partial", "status": "Active", "count": 42},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/docs/TestItem?fields=title", headers=auth_headers)
    assert resp.status_code == 200
    row = resp.json()["data"][0]
    assert "title" in row
    assert "id" in row  # always included
    assert "name" in row  # always included
    assert "status" not in row
    assert "count" not in row
