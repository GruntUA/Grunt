"""Data Import / Export whitelisted methods."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import TYPE_CHECKING, Any, cast

import grunt
from grunt import _
from grunt.data_import.tasks import run_data_import
from grunt.permissions.guards import read_guard, write_guard
from grunt.tasks.broker import broker

if TYPE_CHECKING:
    from grunt.io.doctypes.DataImport.data_import import DataImport


@grunt.whitelist()
async def get_import_preview(data_import_id: str) -> dict[str, Any]:
    """Return column headers, preview rows, and auto-suggested field mapping."""

    di_doc = cast("DataImport", await grunt.get_doc_instance("DataImport", data_import_id))
    return await di_doc.get_import_preview()


@grunt.whitelist()
async def get_import_status(data_import_id: str) -> dict[str, Any]:
    """Return the current status and progress of a DataImport record."""
    doc = await grunt.find_doc("DataImport", data_import_id)
    if not doc:
        grunt.throw(_("DataImport not found"), "NOT_FOUND")
    return {
        "name": doc["name"],
        "status": doc.get("status"),
        "total_rows": doc.get("total_rows") or 0,
        "processed_rows": doc.get("processed_rows") or 0,
        "error_count": doc.get("error_count") or 0,
        "error_log": doc.get("error_log") or [],
    }


@grunt.whitelist()
async def run_import_job(data_import_id: str) -> dict[str, Any]:
    """Start an import job via the background task queue.

    The queued task runs as SYSTEM_USER (it must - the import itself writes
    into whatever target doctype the DataImport record names, which the
    triggering user may have no access to). That makes this check load-
    bearing in a way `get_import_preview`/`get_import_status` aren't: without
    it, any authenticated user who obtains a DataImport id (log line, shared
    link, id guessing) could trigger someone else's privileged bulk-write -
    DataImport is create/write/delete-restricted to "System Manager" for
    exactly this reason, but nothing enforced that restriction on the one
    action that actually executes the write.
    """
    from taskiq import InMemoryBroker

    await write_guard("DataImport", "write")

    if isinstance(broker, InMemoryBroker):
        # No Redis worker running - execute directly in a background asyncio task
        asyncio.create_task(run_data_import(data_import_id))
    else:
        await run_data_import.kiq(data_import_id)

    return {"name": data_import_id, "message": "Import started in background"}


@grunt.whitelist()
async def download_template(doctype: str, fmt: str = "csv") -> dict[str, Any]:
    """Return template data (base64) and filename."""
    from grunt.io.doctypes.DataImport.data_import import DataImport

    await read_guard(doctype)

    try:
        file_bytes, filename = await DataImport.download_template(doctype, fmt=fmt)
        return {
            "filename": filename,
            "content": base64.b64encode(file_bytes).decode("utf-8"),
            "mime_type": "text/csv"
            if fmt == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    except KeyError:
        grunt.throw(_("DocType “%(doctype)s” not found") % {"doctype": doctype}, "NOT_FOUND")


@grunt.whitelist()
async def export_quick(
    doctype: str,
    fmt: str = "csv",
    fields: str | None = None,
    filters: str | None = None,
    limit: int = 10000,
) -> dict[str, Any]:
    """Quick one-shot export returning base64 content."""
    from grunt.io.doctypes.DataImport.data_import import DataImport

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
            "mime_type": "text/csv"
            if fmt == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    except Exception as e:
        grunt.throw(str(e))
