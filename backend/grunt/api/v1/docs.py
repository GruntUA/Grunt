"""Document API endpoints — dynamic CRUD for any DocType."""

from __future__ import annotations

import io
import uuid as _uuid
import csv
from datetime import date, datetime, timezone
from typing import Any
from fastapi.responses import StreamingResponse

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_engine, get_session
from grunt.core.document.service import DocumentService
from grunt.core.metadata.registry import doctype_registry

import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Audit log helper ─────────────────────────────────────────────────────


async def _audit_log(
    session: AsyncSession,
    doctype: str,
    doc_id: str,
    action: str,
    user_email: str,
    changes: dict[str, Any] | None = None,
) -> None:
    """Write an activity entry to grunt_log_activity."""
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    table = compile_doctype_to_table(doctype_registry._doctypes["ActivityLog"])
    entry_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        await session.execute(
            table.insert().values(
                id=entry_id,
                name=entry_id,
                owner=user_email,
                created_at=now,
                modified_at=now,
                modified_by=user_email,
                docstatus=0,
                doctype=doctype,
                doc_id=str(doc_id),
                action=action,
                user=user_email,
                details=changes,
            )
        )
        await session.commit()

        # Broadcast via WebSocket
        try:
            from grunt.api.v1.ws import manager  # noqa: PLC0415
            await manager.broadcast(
                "public:site",
                "activity",
                {
                    "id": entry_id,
                    "doctype": doctype,
                    "doc_id": str(doc_id),
                    "action": action,
                    "user": user_email,
                    "created_at": now.isoformat(),
                }
            )
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        await session.rollback()


# ── Document generation helpers ──────────────────────────────────────────


def _fmt(val: object) -> str:
    """Format a value for human display."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "Так" if val else "Ні"
    if isinstance(val, datetime):
        return val.strftime("%d.%m.%Y %H:%M")
    if isinstance(val, date):
        return val.strftime("%d.%m.%Y")
    return str(val)


def _non_layout_fields(dt: Any) -> list[Any]:
    return [
        f for f in dt.fields
        if f.fieldtype not in ("Section", "Column", "Tab") and not f.hidden
    ]


def _generate_xlsx_single(dt: Any, doc: dict[str, Any]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = dt.label[:31]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2D6A4F")

    ws.merge_cells("A1:B1")
    title_cell = ws["A1"]
    title_cell.value = dt.label
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal="center")

    ws["A2"] = "Поле"
    ws["B2"] = "Значення"
    for cell in [ws["A2"], ws["B2"]]:
        cell.font = header_font
        cell.fill = header_fill

    for i, field in enumerate(_non_layout_fields(dt), start=3):
        ws[f"A{i}"] = field.label
        ws[f"B{i}"] = _fmt(doc.get(field.fieldname))

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 50

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _generate_html_single(dt: Any, doc: dict[str, Any]) -> str:
    rows = ""
    for field in _non_layout_fields(dt):
        val = _fmt(doc.get(field.fieldname))
        rows += f"<tr><th>{field.label}</th><td>{val}</td></tr>\n"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 12pt; margin: 2cm; }}
  h1 {{ color: #2D6A4F; border-bottom: 2px solid #2D6A4F; padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th {{ text-align: left; padding: 8px 12px; background: #f0f4f0; font-weight: bold; width: 40%; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e0e0e0; }}
  .meta {{ color: #666; font-size: 10pt; margin-top: 24px; }}
</style>
</head>
<body>
  <h1>{dt.label}</h1>
  <table>{rows}</table>
  <div class="meta">Створено: {_fmt(doc.get('created_at'))} | Автор: {doc.get('owner', '')}</div>
</body>
</html>"""



def get_doc_service(
    session: AsyncSession = Depends(get_session),
    eng: AsyncEngine = Depends(get_engine),
) -> DocumentService:
    return DocumentService(session, eng)


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/{doctype}")
async def list_documents(
    doctype: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=10000),
    sort_by: str = "modified_at",
    sort_order: str = "desc",
    search: str | None = None,
    fields: str | None = None,
    user: GruntUser = Depends(current_user),
    service: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    # Extract filter[field]=value from query params
    filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            filter_name = key[7:-1]
            filters[filter_name] = value

    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

    return await service.list_documents(
        doctype,
        user,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters if filters else None,
        search=search,
        fields=field_list,
    )


@router.get("/{doctype}/export")
async def export_documents(
    doctype: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    sort_by: str = "modified_at",
    sort_order: str = "desc",
    filters: str | None = None,
    search: str | None = None,
    fields: str | None = None,
) -> StreamingResponse:
    """Export documents as CSV."""
    service = DocumentService(session, engine)
    
    # Parse filters / fields
    parsed_filters: dict[str, Any] = {}
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError:
            # If filters are not valid JSON, ignore them and proceed without filtering.
            logger.debug("Invalid JSON for 'filters' in export_documents; ignoring filters", exc_info=True)
            
    parsed_fields = fields.split(",") if fields else None
    
    # 1. Fetch data (un-paginated for export)
    # We'll fetch in batches if too large, but for now 1000 is fine
    res = await service.list_documents(
        doctype,
        user,
        per_page=1000,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=parsed_filters,
        search=search,
        fields=parsed_fields,
    )
    data = res["data"]
    
    # 2. Generate CSV
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    
    output.seek(0)
    
    filename = f"{doctype}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/{doctype}", status_code=status.HTTP_201_CREATED)
async def create_document(
    doctype: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    doc = await svc.create_document(doctype, body, user)
    await _audit_log(session, doctype, str(doc.get("id", "")), "create", user.email)
    return {"success": True, "data": doc}


@router.get("/{doctype}/{doc_id}")
async def get_document(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    doc = await svc.get_document(doctype, doc_id, user)
    return {"success": True, "data": doc}


@router.put("/{doctype}/{doc_id}")
async def update_document(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    doc = await svc.update_document(doctype, doc_id, body, user)
    await _audit_log(session, doctype, doc_id, "update", user.email, body)
    return {"success": True, "data": doc}


@router.delete("/{doctype}/{doc_id}")
async def delete_document(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await svc.delete_document(doctype, doc_id, user)
    await _audit_log(session, doctype, doc_id, "delete", user.email)
    return {"success": True, "message": "Документ видалено"}


@router.post("/{doctype}/bulk-delete")
async def bulk_delete_documents(
    doctype: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete multiple documents by IDs."""
    ids: list[str] = body.get("ids", [])
    if not ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ids is required")

    deleted = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            await svc.delete_document(doctype, doc_id, user)
            await _audit_log(session, doctype, doc_id, "delete", user.email)
            deleted += 1
        except Exception as e:
            errors.append(f"{doc_id}: {e}")

    return {"success": True, "data": {"deleted": deleted, "errors": errors}}


@router.post("/{doctype}/{doc_id}/transition")
async def apply_workflow_transition(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    eng: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Apply a workflow transition to a document."""
    dt = await doctype_registry.get(doctype)
    from grunt.core.workflow.engine import workflow_engine  # noqa: PLC0415

    updated = await workflow_engine.apply_transition(
        dt, doc_id, body["action"], user, session, eng
    )
    return {"success": True, "data": updated}


@router.get("/{doctype}/{doc_id}/transitions")
async def get_workflow_transitions(
    doctype: str,
    doc_id: str,
    eng: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return available workflow transitions for a document."""
    dt = await doctype_registry.get(doctype)
    if not dt.workflow:
        return {"success": True, "data": []}

    from grunt.core.workflow.engine import workflow_engine  # noqa: PLC0415
    from grunt.core.metadata.compiler import get_table_name  # noqa: PLC0415
    from sqlalchemy import select, Table, MetaData  # noqa: PLC0415

    table_name = get_table_name(dt.module, dt.name)
    meta = MetaData()
    async with eng.connect() as conn:
        table = await conn.run_sync(
            lambda sync_conn: Table(table_name, meta, autoload_with=sync_conn)
        )
        result = await conn.execute(select(table).where(table.c.id == doc_id))
        row = result.mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Документ не знайдено")

    doc = dict(row)
    transitions = await workflow_engine.get_available_transitions(dt, doc, user)
    return {
        "success": True,
        "data": [{"action": t.action, "to_state": t.to_state} for t in transitions],
    }


# ── Document print (single doc) ──────────────────────────────────────────


@router.get("/{doctype}/{doc_id}/print")
async def print_document(
    doctype: str,
    doc_id: str,
    fmt: str = Query("html"),  # html | pdf | xlsx | docx
    print_format: str | None = Query(None),
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Generate document in requested format: html, pdf, xlsx, or docx.

    Args:
        fmt: Output format (html, pdf, xlsx, docx).
        print_format: Name of a custom PrintFormat. If omitted, uses default or standard.
    """
    doc = await svc.get_document(doctype, doc_id, user)
    dt = await doctype_registry.get(doctype)

    if fmt == "xlsx":
        content = _generate_xlsx_single(dt, doc)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.xlsx"'},
        )

    if fmt == "docx":
        from grunt.core.print.renderer import get_print_format_template  # noqa: PLC0415

        pf = await get_print_format_template(session, doctype, print_format)
        if pf and pf[1] == "docx":
            from grunt.core.print.renderer import render_docx  # noqa: PLC0415
            try:
                docx_bytes = render_docx(pf[0], doc)
                return Response(
                    content=docx_bytes,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.docx"'},
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"DOCX generation error: {e}")
        raise HTTPException(
            status_code=404,
            detail="Шаблон DOCX не знайдено. Створіть PrintFormat з template_type='docx'.",
        )

    if fmt in ("pdf", "html"):
        from grunt.core.print.renderer import (  # noqa: PLC0415
            get_print_format_template,
            render_from_string,
            render_standard,
        )

        html = None

        # 1. Try custom PrintFormat from DB
        pf = await get_print_format_template(session, doctype, print_format)
        if pf and pf[1] == "html":
            try:
                html = render_from_string(pf[0], doc, doctype_label=dt.label, fields=dt.fields)
            except Exception:
                pass  # Fall back to standard

        # 2. Standard template (auto-generated from fields)
        if html is None:
            html = render_standard(dt.label, dt.fields, doc)

        if fmt == "html":
            return Response(content=html, media_type="text/html")

        # PDF via WeasyPrint
        try:
            from weasyprint import HTML as WeasyprintHTML  # noqa: PLC0415
            pdf_bytes = WeasyprintHTML(string=html).write_pdf()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.pdf"'},
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="WeasyPrint не встановлено. Використайте fmt=xlsx або fmt=html",
            )

    raise HTTPException(
        status_code=400,
        detail=f"Невідомий формат: {fmt}. Підтримуються: html, pdf, xlsx, docx",
    )


# ── Bulk export ───────────────────────────────────────────────────────────


@router.get("/{doctype}/export/xlsx")
async def export_documents_xlsx(
    doctype: str,
    request: Request,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> Response:
    """Export all documents (up to 10 000) for a DocType as XLSX."""
    filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            filters[key[7:-1]] = value

    result = await svc.list_documents(
        doctype_name=doctype,
        user=user,
        page=1,
        per_page=10000,
        filters=filters if filters else None,
    )
    rows: list[dict[str, Any]] = result["data"]
    dt = await doctype_registry.get(doctype)
    visible = _non_layout_fields(dt)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = dt.label[:31]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2D6A4F")

    # Header row
    headers = ["ID", "Назва", "Власник", "Створено"] + [f.label for f in visible]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        ws.cell(row=row_idx, column=1, value=str(row.get("id", "")))
        ws.cell(row=row_idx, column=2, value=str(row.get("name", "")))
        ws.cell(row=row_idx, column=3, value=str(row.get("owner", "")))
        ws.cell(row=row_idx, column=4, value=_fmt(row.get("created_at")))
        for col_idx, field in enumerate(visible, start=5):
            ws.cell(row=row_idx, column=col_idx, value=_fmt(row.get(field.fieldname)))

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{doctype}_export.xlsx"'},
    )


# ── Version history ───────────────────────────────────────────────────────


@router.get("/{doctype}/{doc_id}/versions")
async def get_document_versions(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Return version history for a document."""
    # Ensure document exists
    await svc.get_document(doctype, doc_id, user)

    from grunt.core.document.versioning import version_service  # noqa: PLC0415

    versions = await version_service.get_versions(session, doctype, doc_id)
    return {"success": True, "data": versions}


@router.post("/{doctype}/{doc_id}/restore/{version_id}")
async def restore_document_version(
    doctype: str,
    doc_id: str,
    version_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Restore a document to a previous version."""
    from grunt.core.document.versioning import version_service  # noqa: PLC0415

    # Get current doc
    current_doc = await svc.get_document(doctype, doc_id, user)

    # Get target version
    target = await version_service.get_version(session, version_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Версію не знайдено")
    if target["doctype"] != doctype or target["doc_id"] != doc_id:
        raise HTTPException(status_code=400, detail="Версія не належить цьому документу")

    # Get all versions for this doc
    all_versions = await version_service.get_versions(session, doctype, doc_id)

    # Build restore data
    restore_data = version_service.build_restore_data(
        current_doc, all_versions, target["version"]
    )

    # Apply as a regular update (will trigger hooks, create new version, etc.)
    # Only include user-data fields, not system fields
    dt = await doctype_registry.get(doctype)
    from grunt.core.metadata.field import NON_PHYSICAL_FIELDS  # noqa: PLC0415

    update_fields = {}
    for field in dt.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue
        if field.fieldname in restore_data:
            update_fields[field.fieldname] = restore_data[field.fieldname]

    result = await svc.update_document(doctype, doc_id, update_fields, user)
    await _audit_log(session, doctype, doc_id, "restore", user.email, {"to_version": target["version"]})

    return {"success": True, "data": result, "restored_to_version": target["version"]}


# ── Document links ───────────────────────────────────────────────────────


@router.get("/{doctype}/{doc_id}/links")
async def get_document_links(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Return all documents that link to this document (backlinks)."""
    await svc.get_document(doctype, doc_id, user)

    from grunt.core.document.links import link_service  # noqa: PLC0415

    links = await link_service.get_backlinks(session, doctype, doc_id)
    return {"success": True, "data": links}


# ── Activity log ──────────────────────────────────────────────────────────


@router.get("/{doctype}/{doc_id}/log")
async def get_document_log(
    doctype: str,
    doc_id: str,
    limit: int = Query(10, ge=1, le=100),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the activity log for a document."""
    from sqlalchemy import select, desc  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    table = compile_doctype_to_table(doctype_registry._doctypes["ActivityLog"])
    q = (
        select(table)
        .where(
            table.c.doctype == doctype,
            table.c.doc_id == doc_id,
        )
        .order_by(desc(table.c.created_at))
        .limit(limit)
    )
    result = await session.execute(q)
    entries = result.mappings().all()
    data = [
        {
            "id": e["id"],
            "action": e["action"],
            "user": e["user"],
            "details": e["details"],
            "created_at": e["created_at"].isoformat() if e["created_at"] else None,
        }
        for e in entries
    ]
    return {"success": True, "data": data}
