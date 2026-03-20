"""Reports API — CRUD and execution of reports."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.db.system_tables import GruntReport

router = APIRouter()


@router.get("/")
async def list_reports(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict:
    """List all reports."""
    result = await session.execute(select(GruntReport))
    reports = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "report_name": r.report_name,
                "report_type": r.report_type,
                "doctype": r.doctype,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
    }


@router.post("/")
async def create_report(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Create a new report."""
    report_name = body.get("report_name", "")
    if not report_name:
        raise HTTPException(status_code=422, detail="report_name є обов'язковим")

    existing = await session.execute(
        select(GruntReport).where(GruntReport.report_name == report_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Звіт '{report_name}' вже існує")

    report = GruntReport(
        report_name=report_name,
        report_type=body.get("report_type", "Query"),
        doctype=body.get("doctype"),
        query=body.get("query"),
        script=body.get("script"),
        columns=body.get("columns"),
        filters_config=body.get("filters_config"),
    )
    session.add(report)
    await session.flush()
    return {"success": True, "data": {"id": str(report.id), "report_name": report.report_name}}


@router.get("/{name}")
async def get_report(
    name: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict:
    """Get a single report by name."""
    result = await session.execute(
        select(GruntReport).where(GruntReport.report_name == name)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")
    return {
        "success": True,
        "data": {
            "id": str(report.id),
            "report_name": report.report_name,
            "report_type": report.report_type,
            "doctype": report.doctype,
            "query": report.query,
            "script": report.script,
            "columns": report.columns,
            "filters_config": report.filters_config,
        },
    }


@router.put("/{name}")
async def update_report(
    name: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Update a report."""
    result = await session.execute(
        select(GruntReport).where(GruntReport.report_name == name)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")

    for field in ("report_type", "doctype", "query", "script", "columns", "filters_config"):
        if field in body:
            setattr(report, field, body[field])

    session.add(report)
    await session.flush()
    return {"success": True, "data": {"report_name": report.report_name}}


@router.delete("/{name}")
async def delete_report(
    name: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Delete a report."""
    result = await session.execute(
        select(GruntReport).where(GruntReport.report_name == name)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")
    await session.delete(report)
    await session.flush()
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
