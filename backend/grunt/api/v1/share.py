"""Document share whitelisted methods."""

from __future__ import annotations
from datetime import UTC, datetime
from typing import Any
import grunt
from grunt.core.doctypes.user.user import SYSTEM_USER

@grunt.whitelist(allow_guest=True)
async def get_shared_document(token: str) -> dict[str, Any]:
    """Return a publicly shared document by token. No authentication required."""
    from grunt.core.metadata.registry import doctype_registry
    from grunt.app import grunt as grunt_app

    # Use SYSTEM_USER for db queries since we are in guest mode
    shares = await grunt.db.get_all(
        "DocumentShare",
        filters={"token": token, "is_active": True},
        limit=1,
    )

    if not shares:
        grunt.throw("Посилання не знайдено або деактивовано", "NOT_FOUND")

    share = shares[0]

    # Check expiry
    expires_at = share.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except ValueError:
                expires_at = None
        if expires_at:
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
            if exp < datetime.now(UTC):
                grunt.throw("Термін дії посилання закінчився", "GONE")

    doctype_name = share["doctype_name"]
    doc_id = share["doc_id"]

    # Continue as SYSTEM_USER to get the document itself
    dt = await doctype_registry.get(doctype_name)
    doc = await grunt.get_doc(doctype_name, doc_id)

    if not doc:
        grunt.throw("Документ не знайдено", "NOT_FOUND")

    # Increment view count (best-effort)
    try:
        current = int(share.get("view_count") or 0)
        await grunt.set_value("DocumentShare", share["id"], "view_count", current + 1)
    except Exception:
        pass

    layout_types = {"Section", "Column", "Tab"}
    visible_fields = [
        {"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype}
        for f in dt.fields
        if f.fieldtype not in layout_types and not f.hidden
    ]

    return {
        "doctype": doctype_name,
        "doctype_label": dt.label,
        "doc_id": doc_id,
        "expires_at": share.get("expires_at"),
        "doc": {k: (str(v) if v is not None else None) for k, v in doc.items()},
        "fields": visible_fields,
    }

@grunt.whitelist()
async def create_share(
    doctype_name: str,
    doc_id: str,
    expires_at: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Create a new document share link. Authenticated users only."""
    if not doctype_name or not doc_id:
        grunt.throw("doctype_name and doc_id are required", "VALIDATION_ERROR")

    doc = await grunt.new_doc(
        "DocumentShare",
        {
            "doctype_name": doctype_name,
            "doc_id": doc_id,
            "expires_at": expires_at,
            "is_active": True,
            "note": note,
        },
    )

    return {"id": doc["id"], "token": doc["token"]}
