"""Data Import / Export whitelisted methods."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, cast
import grunt

if TYPE_CHECKING:
    from grunt.core.doctypes.data_import.data_import import DataImport

@grunt.whitelist()
async def get_import_preview(data_import_id: str) -> dict[str, Any]:
    """Return column headers, preview rows, and auto-suggested field mapping."""
    from grunt.core.doctypes.data_import.data_import import DataImport
    di_doc = cast("DataImport", await grunt.get_doc("DataImport", data_import_id))
    return await di_doc.get_preview()

@grunt.whitelist()
async def get_import_status(data_import_id: str) -> dict[str, Any]:
    """Return the current status and progress of a DataImport record."""
    doc = await grunt.get_doc("DataImport", data_import_id)
    if not doc:
        grunt.throw("DataImport not found", "NOT_FOUND")
    return {
        "id": doc["id"],
        "status": doc.get("status"),
        "total_rows": doc.get("total_rows") or 0,
        "processed_rows": doc.get("processed_rows") or 0,
        "error_count": doc.get("error_count") or 0,
        "error_log": doc.get("error_log") or [],
    }

@grunt.whitelist()
async def run_import_job(data_import_id: str) -> dict[str, Any]:
    """Start an import job (currently triggered synchronously or via task queue)."""
    from grunt.core.doctypes.data_import.data_import import DataImport
    di_doc = cast("DataImport", await grunt.get_doc("DataImport", data_import_id))
    # Note: In a real production setup, this would be queued. 
    # For now, we call .run() which should ideally be non-blocking or handled by the app.
    import asyncio
    asyncio.create_task(di_doc.run()) 
    return {"id": data_import_id, "message": "Import started in background"}

@grunt.whitelist()
async def download_template(doctype: str, fmt: str = "csv") -> dict[str, Any]:
    """Return template data (base64) and filename."""
    from grunt.core.doctypes.data_import.data_import import DataImport
    import base64
    try:
        file_bytes, filename = await DataImport.download_template(doctype, fmt=fmt)
        return {
            "filename": filename,
            "content": base64.b64encode(file_bytes).decode("utf-8"),
            "mime_type": "text/csv" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
    except KeyError:
        grunt.throw(f"DocType '{doctype}' not found", "NOT_FOUND")

@grunt.whitelist()
async def export_quick(
    doctype: str,
    fmt: str = "csv",
    fields: str | None = None,
    filters: str | None = None,
    limit: int = 10000,
) -> dict[str, Any]:
    """Quick one-shot export returning base64 content."""
    from grunt.core.doctypes.data_import.data_import import DataImport
    import json
    import base64

    parsed_filters = json.loads(filters) if filters else None
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None

    try:
        file_bytes, filename = await DataImport.export_doctype(
            grunt,
            doctype,
            filters=parsed_filters,
            fields=parsed_fields,
            fmt=fmt,
            limit=int(limit),
        )
        return {
            "filename": filename,
            "content": base64.b64encode(file_bytes).decode("utf-8"),
            "mime_type": "text/csv" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
    except Exception as e:
        grunt.throw(str(e))
