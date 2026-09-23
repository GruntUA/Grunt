"""Export and Print RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.export_csv   — CSV export (list view)
RPC: grunt.document.base.Document.print        — single doc as html/pdf/xlsx/docx
RPC: grunt.document.base.Document.preview      — render an ad-hoc Jinja2 template
RPC: grunt.document.base.Document.export_file  — bulk export via io registry (any registered format)
"""

from __future__ import annotations

import csv as csv_module
import io
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

import grunt
from grunt.io import get_exporter, get_exporters

_AUTOPRINT_SCRIPT = (
    "<script>"
    "window.onload=function(){"
    "window.print();"
    "window.onafterprint=function(){window.close();};"
    "};"
    "</script>"
)


async def _export_via_registry(
    doctype: str, fmt: str, filters: dict[str, Any] | None = None
) -> Response:
    from grunt.app import grunt as grunt_app

    exporter = get_exporter(fmt)
    if exporter is None:
        available = [e.id for e in get_exporters()]
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий формат '{fmt}'. Доступні: {', '.join(available)}",
        )

    from grunt.api.v1.docs.utils import _non_layout_fields

    dt = await grunt_app.get_meta(doctype)
    if dt is None:
        raise HTTPException(status_code=404, detail=f"DocType «{doctype}» не знайдено")
    fields = _non_layout_fields(dt.doc)
    field_names = [f.fieldname for f in fields]

    rows = await grunt_app.get_list(
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


class DocumentExportRPCMixin:
    """Export/print operations for documents, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def export_csv(
        doctype: str,
        sort_by: str = "modified_at",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        fields: str | None = None,
    ) -> StreamingResponse:
        """Export documents as CSV."""
        from grunt.app import grunt as grunt_app

        parsed_fields = fields.split(",") if fields else ["*"]

        data = await grunt_app.get_list(
            doctype,
            limit=1000,
            order_by=sort_by,
            order=sort_order,
            filters=filters if filters else None,
            search=search,
            fields=parsed_fields,
        )

        output = io.StringIO()
        if data:
            writer = csv_module.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        output.seek(0)

        filename = f"{doctype}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    @grunt.whitelist()
    async def print(
        doctype: str,
        doc_id: str,
        fmt: str = "html",  # html | pdf | xlsx | docx
        print_format: str | None = None,
        autoprint: bool = False,
        token: str | None = None,  # unused: absorbs ?token= consumed by auth, not by us
    ) -> Response:
        """Generate document in requested format: html, pdf, xlsx, or docx."""
        from grunt.app import grunt as grunt_app

        doc = await grunt_app.get_doc(doctype, doc_id)
        dt = await grunt_app.get_meta(doctype)
        if dt is None:
            raise HTTPException(status_code=404, detail=f"DocType «{doctype}» не знайдено")
        session = grunt_app._require_session()

        if fmt == "xlsx":
            from grunt.api.v1.docs.utils import _generate_xlsx_single

            content = _generate_xlsx_single(dt.doc, doc)
            return Response(
                content=content,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.xlsx"'
                },
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
                        media_type=(
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document"
                        ),
                        headers={
                            "Content-Disposition": (
                                f'attachment; filename="{doctype}_{doc_id[:8]}.docx"'
                            )
                        },
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=500, detail=f"DOCX generation error: {e}"
                    ) from e
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

            from grunt.storage.signing import sign_file_urls_in_html

            html = sign_file_urls_in_html(html)
            if fmt == "html":
                if autoprint:
                    html = html.replace("</body>", f"{_AUTOPRINT_SCRIPT}</body>", 1)
                return Response(content=html, media_type="text/html")

            # PDF via headless Chromium (Playwright)
            from grunt.print.pdf import PdfEngineError, html_to_pdf

            try:
                pdf_bytes = await html_to_pdf(html)
            except PdfEngineError as err:
                raise HTTPException(status_code=501, detail=str(err)) from err

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{doctype}_{doc_id[:8]}.pdf"'
                },
            )

        raise HTTPException(
            status_code=400,
            detail=f"Невідомий формат: {fmt}. Підтримуються: html, pdf, xlsx, docx",
        )

    @staticmethod
    @grunt.whitelist()
    async def preview(
        doctype: str,
        template: str,
        doc_id: str | None = None,
    ) -> Response:
        """Render an arbitrary Jinja2 HTML template against a document (or sample)."""
        from grunt.app import grunt as grunt_app
        from grunt.print.renderer import render_from_string

        template_str = (template or "").strip()
        if not template_str:
            raise HTTPException(422, detail="template is required")

        dt = await grunt_app.get_meta(doctype)
        if dt is None:
            raise HTTPException(status_code=404, detail=f"DocType «{doctype}» не знайдено")

        if doc_id:
            doc = await grunt_app.get_doc(doctype, doc_id)
        else:
            # Use first available document as sample
            sample_list = await grunt_app.get_list(doctype, limit=1)
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

        from grunt.storage.signing import sign_file_urls_in_html

        return Response(content=sign_file_urls_in_html(html), media_type="text/html")

    @staticmethod
    @grunt.whitelist()
    async def export_file(
        doctype: str,
        fmt: str = "xlsx",
        filters: dict[str, Any] | None = None,
        token: str | None = None,  # unused: absorbs ?token= consumed by auth, not by us
    ) -> Response:
        """Bulk-export all documents (up to 10 000) for a DocType via the io registry."""
        return await _export_via_registry(doctype, fmt=fmt, filters=filters)
