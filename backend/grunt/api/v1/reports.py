"""Reports API — CRUD and execution of reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Response

from grunt.api.router import GruntRouter
from grunt.app import grunt
from grunt.core.auth.dependencies import superadmin_user

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser

router = GruntRouter(prefix="", tags=["reports"])

_REPORT_FIELDS = [
    "id",
    "report_name",
    "report_type",
    "doctype",
    "query",
    "script",
    "columns",
    "filters_config",
    "created_at",
]


@router.get("/")
async def list_reports() -> dict:
    """"List all reports."""
    data = await grunt.db.get_all(
        "Report",
        fields=["id", "report_name", "report_type", "doctype", "created_at"],
        limit=1000,
        order_by="created_at",
        order="asc",
    )
    return {"success": True, "data": data}


@router.post("/")
async def create_report(
    body: dict,
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Create a new report."""
    report_name = body.get("report_name", "")
    if not report_name:
        raise HTTPException(status_code=422, detail="report_name є обов'язковим")

    existing = await grunt.db.get_all("Report", filters={"report_name": report_name}, limit=1)
    if existing:
        raise HTTPException(status_code=409, detail=f"Звіт '{report_name}' вже існує")

    doc = await grunt.new_doc(
        "Report",
        {
            "report_name": report_name,
            "report_type": body.get("report_type", "Query"),
            "doctype": body.get("doctype"),
            "query": body.get("query"),
            "script": body.get("script"),
            "columns": body.get("columns"),
            "filters_config": body.get("filters_config"),
        },
    )
    return {"success": True, "data": {"id": doc["id"], "report_name": report_name}}


@router.get("/{name}")
async def get_report(
    name: str,
) -> dict:
    """Get a single report by name."""
    report = await grunt.db.get_values("Report", {"report_name": name}, _REPORT_FIELDS)
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")
    return {"success": True, "data": report}


@router.put("/{name}")
async def update_report(
    name: str,
    body: dict,
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Update a report."""
    report = await grunt.db.get_values("Report", {"report_name": name}, ["id"])
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")

    updatable = ("report_type", "doctype", "query", "script", "columns", "filters_config")
    values = {k: body[k] for k in updatable if k in body}
    if values:
        await grunt.save_doc("Report", report["id"], values)
    return {"success": True, "data": {"report_name": name}}


@router.delete("/{name}")
async def delete_report(
    name: str,
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Delete a report."""
    report = await grunt.db.get_values("Report", {"report_name": name}, ["id"])
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")
    await grunt.delete_doc("Report", report["id"])
    return {"success": True, "message": f"Звіт '{name}' видалено"}


@router.post("/{name}/run")
async def run_report(
    name: str,
    body: dict,
) -> dict[str, Any]:
    """Execute a report and return results."""
    from grunt.core.reports.engine import report_engine

    result = await report_engine.run(
        name, body.get("filters", {}), grunt._require_user(), grunt._require_session()
    )
    return {"success": True, **result}


@router.post("/run-preview")
async def run_report_preview(
    body: dict,
) -> dict:
    """Execute an ad-hoc report configuration for preview."""
    from grunt.core.reports.engine import report_engine

    doctype = body.get("doctype")
    if not doctype:
        raise HTTPException(400, detail="Тип документа не вказано")

    result = await report_engine._run_list_report(
        doctype,
        {"columns": body.get("columns", [])},
        body.get("filters", {}),
        grunt._require_user(),
        grunt._require_session(),
    )
    return {"success": True, **result}


@router.get("/{name}/export/xlsx")
async def export_report_xlsx(
    name: str,
) -> Response:
    """Export a report as an Excel file."""
    from grunt.core.reports.engine import report_engine

    result = await report_engine.run(name, {}, grunt._require_user(), grunt._require_session())
    xlsx_bytes = await report_engine.export_excel(result, name)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )
