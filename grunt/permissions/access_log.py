"""Access Log - who took data out and when (PERMISSIONS_PLAN step 6c).

The places that hand data out call :func:`record_access` once the permission
check passed: list exports (every exporter, CSV, quick export, a ``DataExport``
run), printouts of a document (HTML, PDF, XLSX, DOCX), imports and report
downloads - and code elevated to the system on someone's behalf
(``grunt.sudo``, action ``Elevated``, with its reason). A row says who, when,
what (DocType and document, or the filters of an export), in which format and
how many rows.

Written as the system in the request's transaction - a failing write is
logged and never breaks the export it describes.
"""

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.local import require_session, session_user
from grunt.log import log
from grunt.metadata.registry import doctype_registry

LOG_DOCTYPE = "AccessLog"

Action = Literal["Export", "Print", "Import", "Report", "Elevated"]


async def record_access(
    action: Action,
    doctype: str | None,
    *,
    reason: str | None = None,
    doc_id: str | None = None,
    file_format: str | None = None,
    rows: int | None = None,
    filters: Any = None,
    user: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Write an ``AccessLog`` row: *user* (the context's by default) did
    *action* on *doctype* (one document *doc_id*, or rows matching *filters*)."""
    try:
        meta = await doctype_registry.get_meta(LOG_DOCTYPE)
        if meta is None:
            return
        session = session or require_session()
        actor = user or session_user() or ""
        now = datetime.now(UTC)
        async with session.begin_nested():
            await session.execute(
                meta.table.insert().values(
                    name=uuid4().hex[:10],
                    owner=actor,
                    created_at=now,
                    modified_at=now,
                    modified_by=actor,
                    action=action,
                    ref_doctype=doctype,
                    doc_id=doc_id,
                    file_format=(file_format or "").lower() or None,
                    rows=rows,
                    reason=(reason or "")[:255] or None,
                    filters=_jsonable(filters) if filters else None,
                )
            )
    except Exception:
        log.exception("access_log.write_failed", action=action, doctype=doctype)


def _jsonable(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {"text": value}
    return json.loads(json.dumps(value, default=str))
