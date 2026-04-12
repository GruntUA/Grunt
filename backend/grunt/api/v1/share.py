"""Document share endpoints.

GET  /api/v1/public/share/{token}  — no auth, returns shared document
POST /api/v1/share                 — authenticated, creates a new share
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import SYSTEM_USER, GruntUser
from grunt.core.db.session import get_engine, get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

router = APIRouter()


@router.get("/public/share/{token}")
async def get_shared_document(
    token: str,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Return a publicly shared document by token. No authentication required."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    _tokens = grunt.set_context(session, engine, SYSTEM_USER)
    try:
        shares = await grunt.db.get_all(
            "DocumentShare",
            filters={"token": token, "is_active": True},
            limit=1,
        )
    finally:
        grunt.reset_context(_tokens)

    if not shares:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Посилання не знайдено або деактивовано",
        )

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
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Термін дії посилання закінчився",
                )

    doctype_name = share["doctype_name"]
    doc_id = share["doc_id"]

    _tokens = grunt.set_context(session, engine, SYSTEM_USER)
    try:
        dt = await doctype_registry.get(doctype_name)
        doc = await grunt.get_doc(doctype_name, doc_id)

        # Increment view count (best-effort)
        try:
            current = int(share.get("view_count") or 0)
            await grunt.set_value("DocumentShare", share["id"], "view_count", current + 1)
        except Exception:  # noqa: BLE001
            pass
    finally:
        grunt.reset_context(_tokens)

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не знайдено")

    layout_types = {"Section", "Column", "Tab"}
    visible_fields = [
        {"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype}
        for f in dt.fields
        if f.fieldtype not in layout_types and not f.hidden
    ]

    return {
        "success": True,
        "data": {
            "doctype": doctype_name,
            "doctype_label": dt.label,
            "doc_id": doc_id,
            "expires_at": share.get("expires_at"),
            "doc": {k: (str(v) if v is not None else None) for k, v in doc.items()},
            "fields": visible_fields,
        },
    }


@router.post("/share")
async def create_share(
    body: dict[str, Any] = Body(...),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Create a new document share link. Authenticated users only."""
    from grunt.app import grunt  # noqa: PLC0415

    doctype_name: str = body.get("doctype_name", "")
    doc_id: str = body.get("doc_id", "")
    expires_at = body.get("expires_at")
    note: str = body.get("note", "")

    if not doctype_name or not doc_id:
        raise HTTPException(status_code=422, detail="doctype_name and doc_id are required")

    _tokens = grunt.set_context(session, engine, user)
    try:
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
    finally:
        grunt.reset_context(_tokens)

    return {"success": True, "data": {"id": doc["id"], "token": doc["token"]}}
