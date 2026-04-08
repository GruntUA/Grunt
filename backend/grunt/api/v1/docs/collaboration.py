"""Collaboration operations for Documents (Comments, Bookmarks)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from grunt.api.v1.docs.utils import get_doc_service
from grunt.core.auth.dependencies import current_user
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.document.service import DocumentService

router = APIRouter()


@router.get("/{doctype}/{doc_id}/comments")
async def get_document_comments(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all comments for a document."""
    from sqlalchemy import asc  # noqa: PLC0415

    await svc.get_document(doctype, doc_id, user)  # permission check

    table = compile_doctype_to_table(doctype_registry._doctypes["Comment"])
    q = (
        select(table)
        .where(table.c.reference_doctype == doctype, table.c.reference_id == doc_id)
        .order_by(asc(table.c.created_at))
    )
    rows = (await session.execute(q)).mappings().all()
    data = [
        {
            "id": str(r["id"]),
            "content": r["content"],
            "comment_type": r["comment_type"],
            "owner": r["owner"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"success": True, "data": data}


@router.post("/{doctype}/{doc_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_document_comment(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Add a comment to a document. Parses @email mentions."""
    content: str = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="content is required")

    await svc.get_document(doctype, doc_id, user)  # permission check
    comment = await svc.create_document(
        "Comment",
        {
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "content": content,
            "comment_type": body.get("comment_type", "Comment"),
        },
        user,
    )

    # ── @mention notifications ──────────────────────────────────────────
    mentions = set(re.findall(r"@([\w.+\-]+@[\w.\-]+)", content))
    if mentions:
        from grunt.core.notification import notification_service  # noqa: PLC0415

        for mention in mentions:
            if mention == user.email:
                continue
            await notification_service._create_notification(  # noqa: SLF001
                session=session,
                user=mention,
                doctype=doctype,
                doc_id=doc_id,
                subject=f"{user.email} згадав вас у коментарі",
                message=content,
            )
        await session.flush()

    return {"success": True, "data": comment}


@router.delete("/{doctype}/{doc_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_comment(
    doctype: str,
    doc_id: str,
    comment_id: str,
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> None:
    """Delete a comment."""
    comment = await svc.get_document("Comment", comment_id, user)
    if comment.get("owner") != user.email and not user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed")
    await svc.delete_document("Comment", comment_id, user)


@router.get("/{doctype}/{doc_id}/bookmark")
async def get_bookmark(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the current user's bookmark."""
    table = compile_doctype_to_table(doctype_registry._doctypes["Bookmark"])
    q = select(table).where(
        table.c.reference_doctype == doctype,
        table.c.reference_id == doc_id,
        table.c.owner == user.email,
    )
    row = (await session.execute(q)).mappings().first()
    data = dict(row) if row else None
    if data and data.get("created_at"):
        data["created_at"] = data["created_at"].isoformat()
    return {"success": True, "data": data}


@router.post("/{doctype}/{doc_id}/bookmark", status_code=status.HTTP_201_CREATED)
async def add_bookmark(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
    user: GruntUser = Depends(current_user),
    svc: DocumentService = Depends(get_doc_service),
) -> dict[str, Any]:
    """Bookmark a document."""
    await svc.get_document(doctype, doc_id, user)  # permission check
    bookmark = await svc.create_document(
        "Bookmark",
        {
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "title": body.get("title", ""),
        },
        user,
    )
    return {"success": True, "data": bookmark}


@router.delete("/{doctype}/{doc_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(
    doctype: str,
    doc_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    svc: DocumentService = Depends(get_doc_service),
) -> None:
    """Remove a bookmark."""
    table = compile_doctype_to_table(doctype_registry._doctypes["Bookmark"])
    q = select(table).where(
        table.c.reference_doctype == doctype,
        table.c.reference_id == doc_id,
        table.c.owner == user.email,
    )
    row = (await session.execute(q)).mappings().first()
    if row:
        await svc.delete_document("Bookmark", str(row["id"]), user)
