"""Comments and Activity helpers for the grunt.api module.

Business logic lives in the DocType controllers:
  - grunt.core.doctypes.Comment.Comment  (validate, before_delete)
  - grunt.core.doctypes.ActivityLog.ActivityLog  (before_insert)
"""

from __future__ import annotations

from typing import Any

from grunt.app import grunt


# ── Comments ──────────────────────────────────────────────────────────────────


async def add_comment(
    doctype: str,
    doc_id: str,
    text: str,
    is_private: bool = False,
) -> dict[str, Any]:
    """Add a comment to a document."""
    return await grunt.new_doc("Comment", {
        "reference_doctype": doctype,
        "reference_id": doc_id,
        "content": text,
        "comment_type": "Comment",
        "is_private": is_private,
    })


async def get_comments(doctype: str, doc_id: str) -> list[dict[str, Any]]:
    """Get all comments on a document."""
    return await grunt.get_list(
        "Comment",
        filters={"reference_doctype": doctype, "reference_id": doc_id},
        order_by="created_at",
        order="asc",
        limit=1000,
    )


async def delete_comment(comment_id: str) -> None:
    """Delete a comment. Controller enforces ownership check."""
    await grunt.delete_doc("Comment", comment_id)


# ── Activity Log ──────────────────────────────────────────────────────────────


async def log_activity(
    doctype: str,
    doc_id: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log an activity entry. Controller auto-fills user from context."""
    return await grunt.new_doc("ActivityLog", {
        "doctype": doctype,
        "doc_id": doc_id,
        "action": action,
        "details": details,
    })


async def get_activity_log(
    doctype: str,
    doc_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get activity log for a document (newest first)."""
    return await grunt.get_list(
        "ActivityLog",
        filters={"doctype": doctype, "doc_id": doc_id},
        order_by="created_at",
        order="desc",
        limit=limit,
    )
