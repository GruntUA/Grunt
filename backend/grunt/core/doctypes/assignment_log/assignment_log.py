from __future__ import annotations
from typing import Any
import grunt
from grunt.app import grunt as grunt_app
from grunt.core.document.base import Document

class AssignmentLog(Document):
    """AssignmentLog DocType controller."""
    pass

@grunt.whitelist()
async def list_logs(
    doctype: str | None = None,
    document_id: str | None = None,
    assigned_to: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List assignment logs with filters."""
    filters = {}
    if doctype:
        filters["doctype_affected"] = doctype
    if document_id:
        filters["document_id"] = document_id
    if assigned_to:
        filters["assigned_to"] = assigned_to
    if status:
        filters["status"] = status

    logs = await grunt_app.get_list(
        "AssignmentLog", filters=filters, limit=int(limit), order_by="timestamp", order="desc"
    )
    total = await grunt_app.count("AssignmentLog", filters=filters)

    return {"data": logs, "count": total}
