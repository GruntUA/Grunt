"""Document share whitelisted methods."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import grunt
from grunt.log import log


@grunt.whitelist(allow_guest=True)
async def get_shared_document(token: str) -> dict[str, Any]:
    """Return a publicly shared document by token. No authentication required."""
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

    # Fetch without permission guards — this is a guest-accessible share link
    dt = await grunt.get_meta(doctype_name)
    if dt is None:
        grunt.throw("DocType не знайдено", "NOT_FOUND")
    doc = await grunt.db.get_doc(doctype_name, doc_id)

    if not doc:
        grunt.throw("Документ не знайдено", "NOT_FOUND")

    # Increment view count (best-effort)
    try:
        current = int(share.get("view_count") or 0)
        await grunt.set_value("DocumentShare", share["name"], "view_count", current + 1)
    except Exception:
        log.exception("suppressed_error")

    meta = dt
    visible_fields = [
        {"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype}
        for f in meta.get_visible_fields()
    ]

    doc_out = {k: (str(v) if v is not None else None) for k, v in doc.items()}
    await _inject_top_level_link_labels(meta, doc_out)

    return {
        "doctype": doctype_name,
        "doctype_label": dt.label,
        "doc_id": doc_id,
        "expires_at": share.get("expires_at"),
        "doc": doc_out,
        "fields": visible_fields,
    }


async def _inject_top_level_link_labels(meta: Any, doc: dict[str, Any]) -> None:
    """Add ``fieldname__label`` for every Link field present on *doc*.

    The share page is rendered server-side with no client JS to resolve link
    labels itself (unlike the app's ``Link`` field component), so it needs the
    display label baked into the response.
    """
    link_fields = [f for f in meta.doc.fields if f.fieldtype == "Link" and f.options]
    for lf in link_fields:
        raw = doc.get(lf.fieldname)
        if not raw:
            continue
        target_dt = await grunt.get_meta(lf.options)
        if target_dt is None:
            continue

        title_field = target_dt.get_title_field()
        row = await grunt.db.get_values(lf.options, raw, [title_field])
        if row:
            doc[f"{lf.fieldname}__label"] = str(row.get(title_field) or raw)


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

    return {"name": doc["name"], "token": doc["token"]}
