"""Data Import / Export endpoints.

Import
------
GET  /data-import/preview/{id}           — попередній перегляд + маппінг
GET  /data-import/status/{id}            — статус виконання
POST /data-import/run/{id}               — запустити імпорт (фоново)
GET  /data-import/template/{doctype}     — завантажити порожній шаблон (CSV або XLSX)

Export
------
POST /data-import/export/run/{id}        — запустити збережений DataExport (фоново)
GET  /data-import/export/status/{id}     — статус DataExport
GET  /data-import/export/download/{id}   — скачати файл результату
GET  /data-import/export/quick/{doctype} — швидкий експорт без збереження запису
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import Response

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.doctypes.data_import.data_import import DataImport

if TYPE_CHECKING:
    pass

router = GruntRouter(prefix="", tags=["data_import"])

_MIME = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/preview/{data_import_id}")
async def get_import_preview(
    data_import_id: str,
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return column headers, preview rows, and auto-suggested field mapping."""
    di_doc = cast("DataImport", await grunt.get_doc("DataImport", data_import_id))
    result = await di_doc.get_preview()
    return ok(result)


@router.get("/status/{data_import_id}")
async def get_import_status(
    data_import_id: str,
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return the current status and progress of a DataImport record."""
    doc = await grunt.get_doc("DataImport", data_import_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DataImport not found")
    return ok({
        "id": doc["id"],
        "status": doc.get("status"),
        "total_rows": doc.get("total_rows") or 0,
        "processed_rows": doc.get("processed_rows") or 0,
        "error_count": doc.get("error_count") or 0,
        "error_log": doc.get("error_log") or [],
    })


@router.post("/run/{data_import_id}")
async def run_import(
    data_import_id: str,
    background_tasks: BackgroundTasks,
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Start an import job in the background.

    The import runs asynchronously — poll ``GET /status/{id}`` to track progress.
    """
    di_doc = cast("DataImport", await grunt.get_doc("DataImport", data_import_id))
    background_tasks.add_task(di_doc.run)
    return ok({"id": data_import_id, "message": "Import started"})


@router.get("/template/{doctype}")
async def download_template(
    doctype: str,
    fmt: str = Query("csv", pattern="^(csv|xlsx)$"),
    _user: GruntUser = Depends(current_user),
) -> Response:
    """Download an empty import template with column headers for *doctype*.

    ``?fmt=csv`` (default) or ``?fmt=xlsx``
    """
    try:
        file_bytes, filename = await DataImport.download_template(doctype, fmt=fmt)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"DocType '{doctype}' not found")

    return Response(
        content=file_bytes,
        media_type=_MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/quick/{doctype}")
async def export_quick(
    doctype: str,
    fmt: str = Query("csv", pattern="^(csv|xlsx)$"),
    fields: str | None = Query(None, description="Comma-separated fieldnames"),
    filters: str | None = Query(None, description='JSON filter dict, e.g. {"status":"Active"}'),
    limit: int = Query(10_000, ge=1, le=100_000),
    _user: GruntUser = Depends(current_user),
) -> Response:
    """Quick one-shot export — no DataExport record is created.

    Examples::

        GET /data-import/export/quick/Customer?fmt=xlsx
        GET /data-import/export/quick/Customer?fields=name,email&filters={"status":"Active"}
    """
    import json as _json  # noqa: PLC0415

    parsed_filters: dict[str, Any] | None = None
    if filters:
        try:
            parsed_filters = _json.loads(filters)
        except Exception:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="filters must be valid JSON")

    parsed_fields: list[str] | None = None
    if fields:
        parsed_fields = [f.strip() for f in fields.split(",") if f.strip()]

    try:
        file_bytes, filename = await DataImport.export_doctype(
            grunt,
            doctype,
            filters=parsed_filters,
            fields=parsed_fields,
            fmt=fmt,
            limit=limit,
        )
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"DocType '{doctype}' not found")

    return Response(
        content=file_bytes,
        media_type=_MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── DataExport (збережені конфігурації) ────────────────────────────────────────

@router.post("/export/run/{export_id}")
async def run_export(
    export_id: str,
    background_tasks: BackgroundTasks,
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Start a saved DataExport job in the background.

    Poll ``GET /export/status/{id}`` to track progress.
    After completion, download via ``GET /export/download/{id}``.
    """
    from grunt.core.doctypes.data_export.data_export import DataExport  # noqa: PLC0415

    de_doc = cast("DataExport", await grunt.get_doc("DataExport", export_id))
    if not de_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DataExport not found")
    background_tasks.add_task(de_doc.run)
    return ok({"id": export_id, "message": "Export started"})


@router.get("/export/status/{export_id}")
async def get_export_status(
    export_id: str,
    _user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return current status of a DataExport record."""
    doc = await grunt.get_doc("DataExport", export_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DataExport not found")
    return ok({
        "id": doc["id"],
        "status": doc.get("status"),
        "exported_rows": doc.get("exported_rows") or 0,
        "file": doc.get("file"),
        "error": doc.get("error") or "",
    })


@router.get("/export/download/{export_id}")
async def download_export(
    export_id: str,
    _user: GruntUser = Depends(current_user),
) -> Response:
    """Download the result file of a completed DataExport."""
    doc = await grunt.get_doc("DataExport", export_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="DataExport not found")
    if doc.get("status") != "Success":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Export is not ready (status: {doc.get('status')})",
        )

    file_ref = doc.get("file") or ""
    file_id = file_ref.rstrip("/").split("/")[-1]
    if not file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Result file not found")

    from fastapi.responses import RedirectResponse  # noqa: PLC0415

    return RedirectResponse(url=f"/api/v1/files/{file_id}", status_code=status.HTTP_302_FOUND)
