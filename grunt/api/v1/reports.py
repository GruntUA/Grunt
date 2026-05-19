"""Reports whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt.app import grunt as grunt_app


@grunt.whitelist()
async def list_reports() -> list[dict[str, Any]]:
    """List all reports."""
    return await grunt_app.db.get_all(
        "Report",
        fields=["name", "report_name", "report_type", "doctype", "created_at"],
        limit=1000,
        order_by="created_at",
    )


@grunt.whitelist()
async def get_report(name: str) -> dict[str, Any]:
    """Get a single report by name."""
    report = await grunt_app.db.get_values(
        "Report",
        {"report_name": name},
        [
            "name",
            "report_name",
            "report_type",
            "doctype",
            "query",
            "script",
            "columns",
            "filters_config",
            "created_at",
        ],
    )
    if not report:
        grunt_app.throw(f"Звіт '{name}' не знайдено", "NOT_FOUND")
    return report


@grunt.whitelist()
async def save_report(report_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a report. Admin only."""
    if not grunt_app._require_user().is_superadmin:
        grunt_app.throw("Admin only", "PERMISSION_DENIED")

    name = report_data.get("report_name")
    if not name:
        grunt_app.throw("report_name є обов'язковим", "VALIDATION_ERROR")

    existing = await grunt_app.db.get_values("Report", {"report_name": name}, ["name"])
    if existing:
        if report_data.get("__is_new"):
            grunt_app.throw(f"Звіт '{name}' вже існує", "CONFLICT")
        await grunt_app.save_doc("Report", existing["name"], report_data)
        return {"report_name": name, "name": existing["name"]}

    doc = await grunt_app.new_doc("Report", report_data)
    return {"name": doc["name"], "report_name": name}


@grunt.whitelist()
async def delete_report(name: str) -> bool:
    """Delete a report by name. Admin only."""
    if not grunt_app._require_user().is_superadmin:
        grunt_app.throw("Admin only", "PERMISSION_DENIED")

    existing = await grunt_app.db.get_values("Report", {"report_name": name}, ["name"])
    if not existing:
        grunt_app.throw(f"Звіт '{name}' не знайдено", "NOT_FOUND")

    await grunt_app.delete_doc("Report", existing["name"])
    return True


@grunt.whitelist()
async def run_report(name: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a report and return results."""
    from grunt.reports.engine import report_engine

    result = await report_engine.run(
        name, filters or {}, grunt_app._require_user(), grunt_app._require_session()
    )
    return result


@grunt.whitelist()
async def run_preview(
    doctype: str, columns: list[str] | None = None, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute an ad-hoc report configuration for preview."""
    from grunt.reports.engine import report_engine

    result = await report_engine._run_list_report(
        doctype,
        {"columns": columns or []},
        filters or {},
        grunt_app._require_user(),
        grunt_app._require_session(),
    )
    return result
