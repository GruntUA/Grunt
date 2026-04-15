"""Tests for the Document API — dynamic CRUD for DocType instances (migrated to whitelisted methods)."""

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
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.meta.save_doctype", 
        json={"doctype_data": {**TEST_DOCTYPE, "__is_new": True}}, 
        headers=auth_headers
    )
    # We use 200 now instead of 201 because it's a generic method
    assert resp.status_code == 200


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """new_doc → 200 with id/name/owner/created_at."""
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc",
        json={"doctype": "TestItem", "data": {"title": "My First Item", "status": "Draft"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
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
        "/api/v1/method/grunt.api.v1.documents.new_doc",
        json={"doctype": "TestItem", "data": {"status": "Draft"}},
        headers=auth_headers,
    )
    # The whitelisted method dispatcher should catch ValidationError and return 422
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_list → returns created documents."""
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc", 
        json={"doctype": "TestItem", "data": {"title": "Item A"}}, 
        headers=auth_headers
    )
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc", 
        json={"doctype": "TestItem", "data": {"title": "Item B"}}, 
        headers=auth_headers
    )
    
    resp = await client.get(
        "/api/v1/method/grunt.api.v1.documents.get_list", 
        params={"doctype": "TestItem"}, 
        headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert len(body["data"]) == 2
    assert body["meta"]["total"] == 2


@pytest.mark.asyncio
async def test_list_filter_by_status(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_list with filters."""
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc", 
        json={"doctype": "TestItem", "data": {"title": "A", "status": "Draft"}}, 
        headers=auth_headers
    )
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc", 
        json={"doctype": "TestItem", "data": {"title": "B", "status": "Active"}}, 
        headers=auth_headers
    )

    # Note: filters must be a JSON string if passed in query params for whitelisted method
    import json
    filters_str = json.dumps({"status": "Draft"})
    resp = await client.get(
        f"/api/v1/method/grunt.api.v1.documents.get_list?doctype=TestItem&filters={filters_str}", 
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["data"]
    assert len(data) == 1
    assert data[0]["status"] == "Draft"


@pytest.mark.asyncio
async def test_list_search(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_list?search=Alpha."""
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc", 
        json={"doctype": "TestItem", "data": {"title": "Alpha Item"}}, 
        headers=auth_headers
    )
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc", 
        json={"doctype": "TestItem", "data": {"title": "Beta Item"}}, 
        headers=auth_headers
    )

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.documents.get_list", 
        params={"doctype": "TestItem", "search": "Alpha"}, 
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["data"]
    assert len(data) == 1
    assert "Alpha" in data[0]["title"]


@pytest.mark.asyncio
async def test_list_pagination(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_list?page=2&limit=2."""
    for i in range(5):
        await client.post(
            "/api/v1/method/grunt.api.v1.documents.new_doc", 
            json={"doctype": "TestItem", "data": {"title": f"Item {i}"}}, 
            headers=auth_headers
        )

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.documents.get_list", 
        params={"doctype": "TestItem", "page": 2, "limit": 2}, 
        headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["meta"]["total"] == 5
    assert body["meta"]["page"] == 2
    assert body["meta"]["per_page"] == 2
    assert body["meta"]["pages"] == 3
    assert len(body["data"]) == 2


@pytest.mark.asyncio
async def test_get_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_doc → returns the document."""
    create_resp = await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc",
        json={"doctype": "TestItem", "data": {"title": "Single Item"}},
        headers=auth_headers,
    )
    doc_id = create_resp.json()["data"]["id"]

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.documents.get_doc", 
        params={"doctype": "TestItem", "name": doc_id}, 
        headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Single Item"


@pytest.mark.asyncio
async def test_get_nonexistent_404(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_doc nonexistent → 404."""
    resp = await client.get(
        "/api/v1/method/grunt.api.v1.documents.get_doc", 
        params={"doctype": "TestItem", "name": "nonexistent"}, 
        headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """save_doc → modified_at changed."""
    create_resp = await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc",
        json={"doctype": "TestItem", "data": {"title": "Original"}},
        headers=auth_headers,
    )
    doc = create_resp.json()["data"]

    resp = await client.post(
        "/api/v1/method/grunt.api.v1.documents.save_doc",
        json={"doctype": "TestItem", "name": doc["id"], "data": {"title": "Updated"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    updated = resp.json()["data"]
    assert updated["title"] == "Updated"
    assert updated["modified_at"] != doc["modified_at"]


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, auth_headers: dict, setup_doctype):
    """delete_doc → 200, then get_doc → 404."""
    create_resp = await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc",
        json={"doctype": "TestItem", "data": {"title": "ToDelete"}},
        headers=auth_headers,
    )
    doc_id = create_resp.json()["data"]["id"]

    resp = await client.post(
        "/api/v1/method/grunt.api.v1.documents.delete_doc", 
        json={"doctype": "TestItem", "name": doc_id}, 
        headers=auth_headers
    )
    assert resp.status_code == 200

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.documents.get_doc", 
        params={"doctype": "TestItem", "name": doc_id}, 
        headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_partial_fields(client: AsyncClient, auth_headers: dict, setup_doctype):
    """get_list?fields=["title"] → other fields absent."""
    await client.post(
        "/api/v1/method/grunt.api.v1.documents.new_doc",
        json={"doctype": "TestItem", "data": {"title": "Partial", "status": "Active", "count": 42}},
        headers=auth_headers,
    )

    import json
    fields_str = json.dumps(["title"])
    resp = await client.get(
        f"/api/v1/method/grunt.api.v1.documents.get_list?doctype=TestItem&fields={fields_str}", 
        headers=auth_headers
    )
    assert resp.status_code == 200
    row = resp.json()["data"]["data"][0]
    assert "title" in row
    assert "id" in row  # always included
    assert "name" in row  # always included
    assert "status" not in row
    assert "count" not in row
