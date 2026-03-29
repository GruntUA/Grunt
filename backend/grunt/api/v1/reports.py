"""Reports API — CRUD and execution of reports."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

router = APIRouter()


def _report_table():
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    return compile_doctype_to_table(doctype_registry._doctypes["Report"])


@router.get("/")
async def list_reports(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict:
    """List all reports."""
    table = _report_table()
    result = await session.execute(select(table))
    reports = result.mappings().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(r["id"]),
                "report_name": r["report_name"],
                "report_type": r["report_type"],
                "doctype": r["doctype"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
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

    table = _report_table()
    existing = (await session.execute(
        select(table).where(table.c.report_name == report_name)
    )).mappings().first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Звіт '{report_name}' вже існує")

    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await session.execute(
        table.insert().values(
            id=report_id,
            name=report_name,
            owner="system",
            created_at=now,
            modified_at=now,
            modified_by="system",
            docstatus=0,
            report_name=report_name,
            report_type=body.get("report_type", "Query"),
            doctype=body.get("doctype"),
            query=body.get("query"),
            script=body.get("script"),
            columns=body.get("columns"),
            filters_config=body.get("filters_config"),
        )
    )
    await session.flush()
    return {"success": True, "data": {"id": report_id, "report_name": report_name}}


@router.get("/{name}")
async def get_report(
    name: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict:
    """Get a single report by name."""
    table = _report_table()
    result = await session.execute(select(table).where(table.c.report_name == name))
    report = result.mappings().first()
    if not report:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")
    return {
        "success": True,
        "data": {
            "id": str(report["id"]),
            "report_name": report["report_name"],
            "report_type": report["report_type"],
            "doctype": report["doctype"],
            "query": report["query"],
            "script": report["script"],
            "columns": report["columns"],
            "filters_config": report["filters_config"],
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
    table = _report_table()
    existing = (await session.execute(
        select(table).where(table.c.report_name == name)
    )).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")

    values = {k: body[k] for k in ("report_type", "doctype", "query", "script", "columns", "filters_config") if k in body}
    values["modified_at"] = datetime.now(timezone.utc)
    await session.execute(update(table).where(table.c.report_name == name).values(**values))
    await session.flush()
    return {"success": True, "data": {"report_name": name}}


@router.delete("/{name}")
async def delete_report(
    name: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict:
    """Delete a report."""
    table = _report_table()
    existing = (await session.execute(
        select(table).where(table.c.report_name == name)
    )).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail=f"Звіт '{name}' не знайдено")
    await session.execute(delete(table).where(table.c.report_name == name))
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
