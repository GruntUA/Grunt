"""Collaboration RPC methods (Comments, Bookmarks), exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_comments
RPC: grunt.document.base.Document.add_comment
RPC: grunt.document.base.Document.delete_comment
RPC: grunt.document.base.Document.get_bookmark
RPC: grunt.document.base.Document.add_bookmark
RPC: grunt.document.base.Document.remove_bookmark
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status

import grunt
from grunt.i18n import _, language_of, use_language


class DocumentCollaborationRPCMixin:
    """Comments and bookmarks on documents, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_comments(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return all comments for a document."""
        from grunt.permissions.guards import doc_guard

        await doc_guard(doctype, doc_id)

        rows = await grunt.get_list(
            "Comment",
            filters={"reference_doctype": doctype, "reference_id": doc_id},
            order_by="created_at",
            order="asc",
            limit=500,
        )

        return [
            {
                "name": str(r["name"]),
                "content": r.get("content"),
                "comment_type": r.get("comment_type"),
                "owner": r.get("owner"),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
            for r in rows
        ]

    @staticmethod
    @grunt.whitelist()
    async def add_comment(
        doctype: str,
        doc_id: str,
        content: str,
        comment_type: str = "Comment",
    ) -> dict[str, Any]:
        """Add a comment to a document. Parses @email mentions."""
        from grunt.permissions.guards import doc_guard

        content = (content or "").strip()
        if not content:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_("content is required")
            )

        await doc_guard(doctype, doc_id)

        comment = await grunt.new_doc(
            "Comment",
            {
                "reference_doctype": doctype,
                "reference_id": doc_id,
                "content": content,
                "comment_type": comment_type,
            },
        )

        # ── @mention notifications ──────────────────────────────────────────
        mentions = set(re.findall(r"@([\w.+\-]+@[\w.\-]+)", content))
        mentions.discard(grunt.session.user)  # do not notify self
        if mentions:
            for mention in mentions:
                with use_language(await language_of(mention)):
                    subject = _("%(user)s mentioned you in a comment") % {
                        "user": grunt.session.user
                    }
                await grunt.notify(
                    users=[mention],
                    subject=subject,
                    message=content,
                    doctype=doctype,
                    doc_id=doc_id,
                )

        return comment

    @staticmethod
    @grunt.whitelist()
    async def delete_comment(doctype: str, doc_id: str, comment_id: str) -> None:
        """Delete a comment."""

        comment = await grunt.get_doc("Comment", comment_id)
        user = grunt.session
        if comment.get("owner") != user.user and not user.has_role("System Manager"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=_("Not allowed"))

        await grunt.delete_doc("Comment", comment_id)

    @staticmethod
    @grunt.whitelist()
    async def get_bookmark(doctype: str, doc_id: str) -> dict[str, Any] | None:
        """Return the current user's bookmark."""
        from grunt.permissions.guards import doc_guard

        await doc_guard(doctype, doc_id)

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
        return data

    @staticmethod
    @grunt.whitelist()
    async def add_bookmark(doctype: str, doc_id: str, title: str = "") -> dict[str, Any]:
        """Bookmark a document."""
        from grunt.permissions.guards import doc_guard

        await doc_guard(doctype, doc_id)

        return await grunt.new_doc(
            "Bookmark",
            {
                "reference_doctype": doctype,
                "reference_id": doc_id,
                "title": title,
            },
        )

    @staticmethod
    @grunt.whitelist()
    async def remove_bookmark(doctype: str, doc_id: str) -> None:
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
            await grunt.delete_doc("Bookmark", rows[0]["name"])
