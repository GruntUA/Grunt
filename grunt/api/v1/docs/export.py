"""Export and Print operations for Documents."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

import structlog
from fastapi import HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from grunt.api.router import GruntRouter
from grunt.api.v1.docs.utils import _generate_xlsx_single, _non_layout_fields
from grunt.app import grunt
from grunt.io import get_exporter, get_exporters
from grunt.metadata.registry import doctype_registry

logger = structlog.get_logger()
router = GruntRouter(prefix="", tags=["docs", "export"])


@router.get("/{doctype}/export")
async def export_documents(
    doctype: str,
    sort_by: str = "modified_at",
    sort_order: str = "desc",
    filters: str | None = None,
    search: str | None = None,
    fields: str | None = None,
) -> StreamingResponse:
    """Export documents as CSV."""
    parsed_filters: dict[str, Any] = {}
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError:
            logger.debug("export_invalid_filters", doctype=doctype)

    parsed_fields = fields.split(",") if fields else ["*"]

    data = await grunt.get_list(
        doctype,
        limit=1000,
        order_by=sort_by,
        order=sort_order,
        filters=parsed_filters if parsed_filters else None,
        search=search,
        fields=parsed_fields,
    )

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
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{doctype}/{doc_id}/print")
async def print_document(
    doctype: str,
    doc_id: str,
    fmt: str = Query("html"),  # html | pdf | xlsx | docx
    print_format: str | None = Query(None),
) -> Response:
    """Generate document in requested format: html, pdf, xlsx, or docx."""
    doc = await grunt.get_doc(doctype, doc_id)
    dt = await doctype_registry.get(doctype)
    session = grunt._require_session()

    if fmt == "xlsx":
        content = _generate_xlsx_single(dt, doc)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.xlsx"'},
        )

    if fmt == "docx":
        from grunt.print.renderer import get_print_format_template

        pf = await get_print_format_template(session, doctype, print_format)
        if pf and pf[1] == "docx":
            from grunt.print.renderer import render_docx

            try:
                docx_bytes = render_docx(pf[0], doc)
                return Response(
                    content=docx_bytes,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={
                        "Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.docx"'
                    },
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"DOCX generation error: {e}") from e
        raise HTTPException(
            status_code=404,
            detail="Шаблон DOCX не знайдено. Створіть PrintFormat з template_type='docx'.",
        )

    if fmt in ("pdf", "html"):
        from grunt.print.renderer import (
            get_print_format_template,
            render_from_string,
            render_standard,
        )

        html = None

        import contextlib

        # 1. Try custom PrintFormat from DB
        pf = await get_print_format_template(session, doctype, print_format)
        if pf and pf[1] == "html":
            with contextlib.suppress(Exception):
                html = render_from_string(pf[0], doc, doctype_label=dt.label, fields=dt.fields)

        # 2. Standard template (auto-generated from fields)
        if html is None:
            html = render_standard(dt.label, dt.fields, doc)

        if fmt == "html":
            return Response(content=html, media_type="text/html")

        # PDF via WeasyPrint
        try:
            from weasyprint import HTML as WP_HTML

            pdf_bytes = WP_HTML(string=html).write_pdf()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.pdf"'
                },
            )
        except ImportError as err:
            raise HTTPException(
                status_code=501,
                detail="WeasyPrint не встановлено. Використайте fmt=xlsx або fmt=html",
            ) from err

    raise HTTPException(
        status_code=400,
        detail=f"Невідомий формат: {fmt}. Підтримуються: html, pdf, xlsx, docx",
    )


@router.post("/{doctype}/print-preview")
async def print_format_preview(
    doctype: str,
    body: dict[str, Any],
) -> Response:
    """Render an arbitrary Jinja2 HTML template against a document (or sample)."""
    from grunt.print.renderer import render_from_string

    template_str: str = (body.get("template") or "").strip()
    if not template_str:
        raise HTTPException(422, detail="template is required")

    doc_id: str | None = body.get("doc_id")
    dt = await doctype_registry.get(doctype)

    if doc_id:
        doc = await grunt.get_doc(doctype, doc_id)
    else:
        # Use first available document as sample
        sample_list = await grunt.get_list(doctype, limit=1)
        if sample_list:
            doc = sample_list[0]
        else:
            # Synthetic empty doc with all field names set to None
            doc: dict[str, str | None] = {f.fieldname: None for f in dt.fields}
            doc.setdefault("name", "Зразок")

    try:
        html = render_from_string(template_str, doc, doctype_label=dt.label, fields=dt.fields)
    except Exception as e:
        html = f"<pre style='color:red;padding:1rem'>Помилка шаблону:\n{e}</pre>"

    return Response(content=html, media_type="text/html")


@router.get("/{doctype}/export/xlsx")
async def export_documents_xlsx(
    doctype: str,
    request: Request,
) -> Response:
    """Export all documents (up to 10 000) for a DocType — dispatches through io registry."""
    return await _export_via_registry(doctype, fmt="xlsx", request=request)


@router.get("/{doctype}/export/{fmt}")
async def export_documents_fmt(
    doctype: str,
    fmt: str,
    request: Request,
) -> Response:
    """Export documents in any registered format (csv, xlsx, …)."""
    return await _export_via_registry(doctype, fmt=fmt, request=request)


async def _export_via_registry(doctype: str, fmt: str, request: Request) -> Response:
    exporter = get_exporter(fmt)
    if exporter is None:
        available = [e.id for e in get_exporters()]
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий формат '{fmt}'. Доступні: {', '.join(available)}",
        )

    filters: dict[str, str] = {}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]"):
            filters[key[7:-1]] = value

    dt = await doctype_registry.get(doctype)
    fields = _non_layout_fields(dt)
    field_names = [f.fieldname for f in fields]

    rows = await grunt.get_list(
        doctype,
        limit=10_000,
        filters=filters if filters else None,
        fields=field_names,
    )

    content = await exporter.export(doctype, rows, fields)
    filename = exporter.filename(doctype)

    return Response(
        content=content,
        media_type=exporter.content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
