"""Tests for the Reports module (migrated to whitelisted methods)."""

from __future__ import annotations

import pytest

# Direct API tests don't need AsyncClient

# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_create_and_list_report(ctx):
    """Create a report and list it."""
    from grunt.api.v1.reports import list_reports, save_report

    # Create
    await save_report(
        report_data={
            "report_name": "Users Report",
            "report_type": "Query",
            "query": "SELECT 1 as num",
        }
    )
    await ctx.db._session().commit()

    # List
    reports = await list_reports()
    assert any(r["report_name"] == "Users Report" for r in reports)


@pytest.mark.asyncio
async def test_get_report(ctx):
    """Get a single report by name."""
    from grunt.api.v1.reports import get_report, save_report

    await save_report(
        report_data={
            "report_name": "My Report",
            "report_type": "Query",
            "query": "SELECT 42 as answer",
        }
    )
    await ctx.db._session().commit()

    data = await get_report(name="My Report")
    assert data["report_name"] == "My Report"


@pytest.mark.asyncio
async def test_run_query_report(ctx):
    """Run a SELECT query report."""
    from grunt.api.v1.reports import run_report, save_report

    await save_report(
        report_data={
            "report_name": "Select Report",
            "report_type": "Query",
            "query": "SELECT 42 as answer",
        }
    )
    await ctx.db._session().commit()

    data = await run_report(name="Select Report", filters={})
    assert data["data"][0]["answer"] == 42


@pytest.mark.asyncio
async def test_run_report_forbids_delete(ctx):
    """DELETE SQL is blocked in query reports."""
    from fastapi import HTTPException

    from grunt.api.v1.reports import run_report, save_report

    await save_report(
        report_data={
            "report_name": "Bad Report",
            "report_type": "Query",
            "query": "DELETE FROM grunt_auth_user",
        }
    )
    await ctx.db._session().commit()

    from grunt.api.messages import ApplicationError
    from grunt.errors import GruntError

    with pytest.raises((HTTPException, ApplicationError, GruntError)):
        await run_report(name="Bad Report", filters={})
    # Business logic error should be caught


@pytest.mark.asyncio
async def test_delete_report(ctx):
    """Delete a report."""

    from grunt.api.v1.reports import delete_report, get_report, save_report

    await save_report(
        report_data={"report_name": "Delete Me", "report_type": "Query", "query": "SELECT 1"}
    )
    await ctx.db._session().commit()

    await delete_report(name="Delete Me")
    await ctx.db._session().commit()

    from grunt.errors import GruntError

    with pytest.raises(GruntError) as excinfo:
        await get_report(name="Delete Me")
    assert "не знайдено" in str(excinfo.value)


@pytest.mark.asyncio
async def test_duplicate_report_rejected(ctx):
    """Creating a report with duplicate name returns 409."""

    from grunt.api.v1.reports import save_report

    payload = {"report_name": "Dup", "report_type": "Query", "query": "SELECT 1"}
    await save_report(report_data=payload)
    await ctx.db._session().commit()

    # Second call with __is_new: True
    from grunt.errors import GruntError

    with pytest.raises(GruntError) as excinfo:
        await save_report(report_data={**payload, "__is_new": True})
    assert "вже існує" in str(excinfo.value)


@pytest.mark.asyncio
async def test_apps_crud(ctx):
    """Apps CRUD directly."""
    from grunt.core.doctypes.grunt_installed_app.grunt_installed_app import (
        delete_app,
        list_apps,
        register_app,
    )

    # Create (register_app)
    await register_app(name="crm", title="CRM App", version="1.0.0")
    await ctx.db._session().commit()

    # List (list_apps)
    apps = await list_apps()
    assert any(a["name"] == "crm" for a in apps)

    # Delete (delete_app)
    await delete_app(name="crm")
    await ctx.db._session().commit()

    # Verify deleted
    apps = await list_apps()
    assert not any(a["name"] == "crm" for a in apps)
