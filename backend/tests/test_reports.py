"""Tests for the Reports module."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_report(client: AsyncClient, auth_headers: dict):
    """Create a report and list it."""
    # Create
    resp = await client.post(
        "/api/v1/reports/",
        json={
            "report_name": "Users Report",
            "report_type": "Query",
            "query": "SELECT 1 as num",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["report_name"] == "Users Report"

    # List
    resp = await client.get("/api/v1/reports/", headers=auth_headers)
    assert resp.status_code == 200
    reports = resp.json()["data"]
    assert any(r["report_name"] == "Users Report" for r in reports)


@pytest.mark.asyncio
async def test_get_report(client: AsyncClient, auth_headers: dict):
    """Get a single report by name."""
    await client.post(
        "/api/v1/reports/",
        json={"report_name": "My Report", "report_type": "Query", "query": "SELECT 42 as answer"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/reports/My Report", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["report_name"] == "My Report"


@pytest.mark.asyncio
async def test_run_query_report(client: AsyncClient, auth_headers: dict):
    """Run a SELECT query report."""
    await client.post(
        "/api/v1/reports/",
        json={"report_name": "Select Report", "report_type": "Query", "query": "SELECT 42 as answer"},
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v1/reports/Select Report/run",
        json={"filters": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"][0]["answer"] == 42


@pytest.mark.asyncio
async def test_run_report_forbids_delete(client: AsyncClient, auth_headers: dict):
    """DELETE SQL is blocked in query reports."""
    await client.post(
        "/api/v1/reports/",
        json={"report_name": "Bad Report", "report_type": "Query", "query": "DELETE FROM grunt_auth_user"},
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v1/reports/Bad Report/run",
        json={"filters": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_report(client: AsyncClient, auth_headers: dict):
    """Delete a report."""
    await client.post(
        "/api/v1/reports/",
        json={"report_name": "Delete Me", "report_type": "Query", "query": "SELECT 1"},
        headers=auth_headers,
    )

    resp = await client.delete("/api/v1/reports/Delete Me", headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/reports/Delete Me", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_report_rejected(client: AsyncClient, auth_headers: dict):
    """Creating a report with duplicate name returns 409."""
    payload = {"report_name": "Dup", "report_type": "Query", "query": "SELECT 1"}
    await client.post("/api/v1/reports/", json=payload, headers=auth_headers)
    resp = await client.post("/api/v1/reports/", json=payload, headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_apps_crud(client: AsyncClient, auth_headers: dict):
    """Apps CRUD: create, list, delete."""
    # Create
    resp = await client.post(
        "/api/v1/apps/",
        json={"name": "crm", "title": "CRM App", "version": "1.0.0"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # List
    resp = await client.get("/api/v1/apps/", headers=auth_headers)
    assert resp.status_code == 200
    apps = resp.json()["data"]
    assert any(a["name"] == "crm" for a in apps)

    # Delete
    resp = await client.delete("/api/v1/apps/crm", headers=auth_headers)
    assert resp.status_code == 200

    # Verify deleted
    resp = await client.get("/api/v1/apps/", headers=auth_headers)
    apps = resp.json()["data"]
    assert not any(a["name"] == "crm" for a in apps)
