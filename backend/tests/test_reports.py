"""Tests for the Reports module (migrated to whitelisted methods)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

# ── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_report(client: AsyncClient, auth_headers: dict):
    """Create a report and list it."""
    # Create
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.reports.save_report",
        json={
            "report_data": {
                "report_name": "Users Report",
                "report_type": "Query",
                "query": "SELECT 1 as num",
            }
        },
        headers=auth_headers,
    )
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200
    assert resp.json()["data"]["report_name"] == "Users Report"

    # List
    resp = await client.get("/api/v1/method/grunt.api.v1.reports.list_reports", headers=auth_headers)
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200
    reports = resp.json()["data"]
    assert any(r["report_name"] == "Users Report" for r in reports)


@pytest.mark.asyncio
async def test_get_report(client: AsyncClient, auth_headers: dict):
    """Get a single report by name."""
    await client.post(
        "/api/v1/method/grunt.api.v1.reports.save_report",
        json={
            "report_data": {
                "report_name": "My Report", 
                "report_type": "Query", 
                "query": "SELECT 42 as answer"
            }
        },
        headers=auth_headers,
    )

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.reports.get_report", 
        params={"name": "My Report"}, 
        headers=auth_headers
    )
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200
    assert resp.json()["data"]["report_name"] == "My Report"


@pytest.mark.asyncio
async def test_run_query_report(client: AsyncClient, auth_headers: dict):
    """Run a SELECT query report."""
    await client.post(
        "/api/v1/method/grunt.api.v1.reports.save_report",
        json={
            "report_data": {
                "report_name": "Select Report",
                "report_type": "Query",
                "query": "SELECT 42 as answer",
            }
        },
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v1/method/grunt.api.v1.reports.run_report",
        json={"name": "Select Report", "filters": {}},
        headers=auth_headers,
    )
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["data"][0]["answer"] == 42


@pytest.mark.asyncio
async def test_run_report_forbids_delete(client: AsyncClient, auth_headers: dict):
    """DELETE SQL is blocked in query reports."""
    await client.post(
        "/api/v1/method/grunt.api.v1.reports.save_report",
        json={
            "report_data": {
                "report_name": "Bad Report",
                "report_type": "Query",
                "query": "DELETE FROM grunt_auth_user",
            }
        },
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v1/method/grunt.api.v1.reports.run_report",
        json={"name": "Bad Report", "filters": {}},
        headers=auth_headers,
    )
    # The report engine should throw an error which results in 422 or 400
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_delete_report(client: AsyncClient, auth_headers: dict):
    """Delete a report."""
    await client.post(
        "/api/v1/method/grunt.api.v1.reports.save_report",
        json={"report_data": {"report_name": "Delete Me", "report_type": "Query", "query": "SELECT 1"}},
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v1/method/grunt.api.v1.reports.delete_report", 
        json={"name": "Delete Me"}, 
        headers=auth_headers
    )
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.reports.get_report", 
        params={"name": "Delete Me"}, 
        headers=auth_headers
    )
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_duplicate_report_rejected(client: AsyncClient, auth_headers: dict):
    """Creating a report with duplicate name returns 409."""
    payload = {
        "report_data": {"report_name": "Dup", "report_type": "Query", "query": "SELECT 1"}
    }
    await client.post("/api/v1/method/grunt.api.v1.reports.save_report", json=payload, headers=auth_headers)
    
    # Second call with __is_new: True
    payload_conflict = {
        "report_data": {**payload["report_data"], "__is_new": True}
    }
    resp = await client.post("/api/v1/method/grunt.api.v1.reports.save_report", json=payload_conflict, headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_apps_crud(client: AsyncClient, auth_headers: dict):
    """Apps CRUD: create, list, delete."""
    # Create (register_app)
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.apps.register_app",
        json={"name": "crm", "title": "CRM App", "version": "1.0.0"},
        headers=auth_headers,
    )
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200

    # List (list_apps)
    resp = await client.get("/api/v1/method/grunt.api.v1.apps.list_apps", headers=auth_headers)
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200
    apps = resp.json()["data"]
    assert any(a["name"] == "crm" for a in apps)

    # Delete (delete_app)
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.apps.delete_app", 
        json={"name": "crm"}, 
        headers=auth_headers
    )
    if resp.status_code != 200:
        print(f"DEBUG: Save report failed: {resp.status_code} - {resp.text}")
    assert resp.status_code == 200

    # Verify deleted
    resp = await client.get("/api/v1/method/grunt.api.v1.apps.list_apps", headers=auth_headers)
    apps = resp.json()["data"]
    assert not any(a["name"] == "crm" for a in apps)
