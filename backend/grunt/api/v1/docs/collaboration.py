"""Collaboration operations for Documents (Comments, Bookmarks)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt

router = GruntRouter(prefix="", tags=["docs", "collaboration"])


@router.get("/{doctype}/{doc_id}/comments")
async def get_document_comments(
    doctype: str,
    doc_id: str,
) -> dict[str, Any]:
    """Return all comments for a document."""
    await grunt.get_doc(doctype, doc_id)  # permission check

    rows = await grunt.get_list(
        "Comment",
        filters={"reference_doctype": doctype, "reference_id": doc_id},
        order_by="created_at",
        order="asc",
        limit=500,
    )

    data = [
        {
            "id": str(r["id"]),
            "content": r.get("content"),
            "comment_type": r.get("comment_type"),
            "owner": r.get("owner"),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
        }
        for r in rows
    ]
    return ok(data)


@router.post("/{doctype}/{doc_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_document_comment(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Add a comment to a document. Parses @email mentions."""
    content: str = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="content is required")

    await grunt.get_doc(doctype, doc_id)  # permission check

    comment = await grunt.new_doc(
        "Comment",
        {
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "content": content,
            "comment_type": body.get("comment_type", "Comment"),
        },
    )

    # ── @mention notifications ──────────────────────────────────────────
    mentions = set(re.findall(r"@([\w.+\-]+@[\w.\-]+)", content))
    mentions.discard(grunt.session.user)  # do not notify self
    if mentions:
        for mention in mentions:
            await grunt.notify(
                users=[mention],
                subject=f"{grunt.session.user} згадав вас у коментарі",
                message=content,
                doctype=doctype,
                doc_id=doc_id,
            )

    return ok(comment)


@router.delete("/{doctype}/{doc_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_comment(
    doctype: str,
    doc_id: str,
    comment_id: str,
) -> None:
    """Delete a comment."""
    comment = await grunt.get_doc("Comment", comment_id)
    user = grunt.session
    if comment.get("owner") != user.user and not user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed")

    await grunt.delete_doc("Comment", comment_id)


@router.get("/{doctype}/{doc_id}/bookmark")
async def get_bookmark(
    doctype: str,
    doc_id: str,
) -> dict[str, Any]:
    """Return the current user's bookmark."""
    await grunt.get_doc(doctype, doc_id)

    rows = await grunt.get_list(
        "Bookmark",
        filters={
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "owner": grunt.session.user,
        },
        limit=1,
    )

    data = dict(rows[0]) if rows else None
    if data and data.get("created_at"):
        data["created_at"] = str(data["created_at"])
    return ok(data)


@router.post("/{doctype}/{doc_id}/bookmark", status_code=status.HTTP_201_CREATED)
async def add_bookmark(
    doctype: str,
    doc_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Bookmark a document."""
    await grunt.get_doc(doctype, doc_id)  # permission check

    bookmark = await grunt.new_doc(
        "Bookmark",
        {
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "title": body.get("title", ""),
        },
    )
    return ok(bookmark)


@router.delete("/{doctype}/{doc_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(
    doctype: str,
    doc_id: str,
) -> None:
    """Remove a bookmark."""
    rows = await grunt.get_list(
        "Bookmark",
        filters={
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "owner": grunt.session.user,
        },
        limit=1,
    )
    if rows:
        await grunt.delete_doc("Bookmark", rows[0]["id"])
