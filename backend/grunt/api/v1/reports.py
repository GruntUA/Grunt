"""Reports API — CRUD and execution of reports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.app import grunt
from grunt.core.auth.dependencies import current_user, grunt_context, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

router = APIRouter()

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
async def list_reports(
    _: None = Depends(grunt_context),
) -> dict:
    """List all reports."""
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
    __: None = Depends(grunt_context),
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
    _: None = Depends(grunt_context),
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
    __: None = Depends(grunt_context),
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
    __: None = Depends(grunt_context),
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
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Execute a report and return results."""
    from grunt.core.reports.engine import report_engine  # noqa: PLC0415

    result = await report_engine.run(name, body.get("filters", {}), user, session)
    return {"success": True, **result}


@router.post("/run-preview")
async def run_report_preview(
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Execute an ad-hoc report configuration for preview."""
    from grunt.core.reports.engine import report_engine  # noqa: PLC0415

    doctype = body.get("doctype")
    if not doctype:
        raise HTTPException(400, detail="Тип документа не вказано")

    result = await report_engine._run_list_report(
        doctype,
        {"columns": body.get("columns", [])},
        body.get("filters", {}),
        user,
        session,
    )
    return {"success": True, **result}


@router.get("/{name}/export/xlsx")
async def export_report_xlsx(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> Response:
    """Export a report as an Excel file."""
    from grunt.core.reports.engine import report_engine  # noqa: PLC0415

    result = await report_engine.run(name, {}, user, session)
    xlsx_bytes = await report_engine.export_excel(result, name)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )
