"""Comments and Activity API for documents.

Example:
    from grunt import Doc

    doc = await Doc.get("Invoice", "INV-001")
    await doc.add_comment("Approved for payment")

    comments = await doc.get_comments()
    for comment in comments:
        print(f"{comment['author']}: {comment['text']}")
"""

from typing import Any
from datetime import datetime

from sqlalchemy import select, insert, delete

from grunt.api.context import get_session, get_user
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry


class Comment:
    """Comment on a document."""

    def __init__(
        self,
        id: str,
        doctype: str,
        doc_id: str,
        author: str,
        author_name: str,
        text: str,
        is_private: bool = False,
        created_at: str | None = None,
    ):
        self.id = id
        self.doctype = doctype
        self.doc_id = doc_id
        self.author = author
        self.author_name = author_name
        self.text = text
        self.is_private = is_private
        self.created_at = created_at or datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "doctype": self.doctype,
            "doc_id": self.doc_id,
            "author": self.author,
            "author_name": self.author_name,
            "text": self.text,
            "is_private": self.is_private,
            "created_at": self.created_at,
        }


async def add_comment(
    doctype: str,
    doc_id: str,
    text: str,
    is_private: bool = False,
) -> Comment:
    """Add a comment to a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID
        text: Comment text
        is_private: If True, only visible to creator and superadmin

    Returns:
        Comment object

    Example:
        await add_comment("Invoice", "INV-001", "This invoice is approved")
    """
    session = get_session()
    user = get_user()

    import uuid

    comment_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # TODO: Store in database (Comment DocType or comments table)
    # For now, return in-memory comment
    comment = Comment(
        id=comment_id,
        doctype=doctype,
        doc_id=doc_id,
        author=user.email,
        author_name=user.full_name,
        text=text,
        is_private=is_private,
        created_at=now,
    )

    return comment


async def get_comments(doctype: str, doc_id: str) -> list[Comment]:
    """Get all comments on a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID

    Returns:
        List of Comment objects

    Example:
        comments = await get_comments("Invoice", "INV-001")
        for comment in comments:
            print(f"{comment.author_name}: {comment.text}")
    """
    session = get_session()
    user = get_user()

    # TODO: Query from database (Comment DocType)
    # For now, return empty list
    return []


async def delete_comment(comment_id: str) -> None:
    """Delete a comment (only owner or superadmin can delete).

    Args:
        comment_id: Comment ID to delete
    """
    session = get_session()
    user = get_user()

    # TODO: Verify ownership or superadmin status
    # TODO: Delete from database
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Activity Logging
# ─────────────────────────────────────────────────────────────────────────────


class ActivityEntry:
    """Single activity/audit log entry."""

    def __init__(
        self,
        doctype: str,
        doc_id: str,
        action: str,
        user_email: str | None = None,
        details: dict[str, Any] | None = None,
        created_at: str | None = None,
    ):
        self.doctype = doctype
        self.doc_id = doc_id
        self.action = action
        self.user_email = user_email
        self.details = details or {}
        self.created_at = created_at or datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doctype": self.doctype,
            "doc_id": self.doc_id,
            "action": self.action,
            "user_email": self.user_email,
            "details": self.details,
            "created_at": self.created_at,
        }


async def log_activity(
    doctype: str,
    doc_id: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> ActivityEntry:
    """Log an activity/audit entry for a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID
        action: Action name (e.g., "created", "updated", "submitted", "deleted")
        details: Optional dict with additional context

    Returns:
        ActivityEntry object

    Example:
        await log_activity(
            doctype="Invoice",
            doc_id="INV-001",
            action="submitted",
            details={"old_status": "Draft", "new_status": "Submitted"}
        )
    """
    session = get_session()
    user = get_user()

    entry = ActivityEntry(
        doctype=doctype,
        doc_id=doc_id,
        action=action,
        user_email=user.email,
        details=details,
    )

    # TODO: Store in ActivityLog table
    # For now, just log to structlog
    import structlog

    logger = structlog.get_logger()
    logger.info(
        "activity.logged",
        doctype=doctype,
        doc_id=doc_id,
        action=action,
        user=user.email,
        details=details,
    )

    return entry


async def get_activity_log(
    doctype: str,
    doc_id: str,
    limit: int = 100,
) -> list[ActivityEntry]:
    """Get activity log for a document.

    Args:
        doctype: e.g., "Invoice"
        doc_id: Document ID
        limit: Maximum number of entries to return

    Returns:
        List of ActivityEntry objects (newest first)

    Example:
        log = await get_activity_log("Invoice", "INV-001", limit=50)
        for entry in log:
            print(f"{entry.action} by {entry.user_email} at {entry.created_at}")
    """
    session = get_session()

    # TODO: Query from ActivityLog table with limit and ordering
    # For now, return empty list
    return []
