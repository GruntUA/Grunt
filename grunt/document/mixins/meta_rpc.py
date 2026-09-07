"""Cross-document metadata RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_backlinks
RPC: grunt.document.base.Document.get_sidebar
"""

from __future__ import annotations

from typing import Any

import grunt


def _iso(value: Any) -> str | None:
    return str(value) if value else None


async def _optional(coro: Any, fallback: Any) -> Any:
    """Await *coro*, returning *fallback* if it fails with a permission error.

    The sidebar bundles several auxiliary sections (assignees, shares, tags,
    bookmark). A viewer who lacks read on one of those system DocTypes should
    just get an empty section — not a failed sidebar and a stray "access
    denied" toast.
    """
    from fastapi import HTTPException

    try:
        return await coro
    except HTTPException as exc:
        if exc.status_code == 403:
            return fallback
        raise


class DocumentMetaRPCMixin:
    """Cross-document metadata (backlinks, sidebar bundle), exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_backlinks(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return all documents that link to this document (backlinks)."""
        from grunt.app import grunt as grunt_app

        # Permission verification
        await grunt_app.get_doc(doctype, doc_id)

        from grunt.document.links import link_service

        return await link_service.get_backlinks(grunt_app._require_session(), doctype, doc_id)

    @staticmethod
    @grunt.whitelist()
    async def get_sidebar(doctype: str, doc_id: str) -> dict[str, Any]:
        """Return the whole document-sidebar payload in one round-trip.

        Bundles assignees, shares, tags, backlinks and the current user's
        bookmark so the desk sidebar needs a single request instead of one
        per section.
        """
        from grunt.app import grunt as grunt_app

        doc = await grunt_app.get_doc(doctype, doc_id)  # also the permission check

        ref = {"reference_doctype": doctype, "reference_id": doc_id}

        # Auxiliary sections — a viewer who can't read one of these system
        # DocTypes just gets an empty section, not a broken sidebar.
        assignees = await _optional(
            grunt_app.get_list(
                "ToDo",
                filters={**ref, "status__in": ["Open", "In Progress"]},
                order_by="created_at",
                order="asc",
                limit=100,
            ),
            [],
        )
        shares = await _optional(
            grunt_app.get_list(
                "SharedWith", filters=ref, order_by="created_at", order="asc", limit=100
            ),
            [],
        )
        tags = await _optional(
            grunt_app.get_list(
                "DocTag", filters=ref, order_by="created_at", order="asc", limit=100
            ),
            [],
        )
        bookmarks = await _optional(
            grunt_app.get_list(
                "Bookmark",
                filters={**ref, "owner": grunt_app.session.user},
                limit=1,
            ),
            [],
        )

        from grunt.document.links import link_service

        backlinks = await _optional(
            link_service.get_backlinks(grunt_app._require_session(), doctype, doc_id),
            [],
        )

        bookmark = dict(bookmarks[0]) if bookmarks else None
        if bookmark and bookmark.get("created_at"):
            bookmark["created_at"] = _iso(bookmark["created_at"])

        # Resolve display names/avatars for everyone referenced in the sidebar.
        emails: set[str] = set()
        for value in (doc.get("owner"), doc.get("modified_by")):
            if value:
                emails.add(value)
        for row in assignees:
            if row.get("assigned_to"):
                emails.add(row["assigned_to"])
        for row in shares:
            if row.get("user"):
                emails.add(row["user"])

        people: dict[str, dict[str, Any]] = {}
        if emails:
            from grunt.auth.doctypes.User.user import get_user_by_email

            for email in emails:
                u = await get_user_by_email(email)
                if u is None:
                    continue
                people[email] = {
                    "name": getattr(u, "full_name", None) or email,
                    "avatar": u.data.get("avatar") or None,
                }

        return {
            "assignees": [
                {
                    "name": str(r["name"]),
                    "assigned_to": r.get("assigned_to"),
                    "description": r.get("description"),
                    "created_at": _iso(r.get("created_at")),
                    "status": r.get("status"),
                    "priority": r.get("priority"),
                    "due_date": r.get("due_date"),
                    "is_overdue": bool(r.get("is_overdue")),
                }
                for r in assignees
            ],
            "shares": [
                {
                    "name": str(r["name"]),
                    "user": r.get("user"),
                    "permission": r.get("permission"),
                }
                for r in shares
            ],
            "tags": [
                {"name": str(r["name"]), "tag": r.get("tag")}
                for r in tags
            ],
            "backlinks": backlinks,
            "bookmark": bookmark,
            "people": people,
        }
