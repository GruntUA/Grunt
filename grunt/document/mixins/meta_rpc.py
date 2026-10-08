"""Cross-document metadata RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_backlinks
RPC: grunt.document.base.Document.get_sidebar
RPC: grunt.document.base.Document.get_preview
RPC: grunt.document.base.Document.get_field_years
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt.i18n import _


def _iso(value: Any) -> str | None:
    return str(value) if value else None


async def _optional(coro: Any, fallback: Any) -> Any:
    """Await *coro*, returning *fallback* if it fails with a permission error.

    The sidebar bundles several auxiliary sections (assignees, shares, tags,
    bookmark). A viewer who lacks read on one of those system DocTypes should
    just get an empty section - not a failed sidebar and a stray "access
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
    async def get_field_years(doctype: str, fieldname: str) -> list[int]:
        """Years present in a Date/Datetime field, newest first (year quick filter)."""
        from grunt.document import collection
        from grunt.permissions.guards import read_guard

        _dt, user, hidden_fields = await read_guard(doctype)
        if fieldname in hidden_fields:
            return []
        return await collection.field_years(grunt.get_session(), doctype, user, fieldname)

    @staticmethod
    @grunt.whitelist()
    async def get_backlinks(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return all documents that link to this document (backlinks).

        Each row carries ``title`` - the source document's title_field value
        (permission-aware, one query per source DocType), falling back to its id.
        """

        # Permission verification
        await grunt.get_doc(doctype, doc_id)

        from grunt.document.links import link_service
        from grunt.document.titles import resolve_reference_titles

        rows = await link_service.get_backlinks(grunt.get_session(), doctype, doc_id)
        refs = [(r["source_doctype"], r["source_id"]) for r in rows]
        titles = await resolve_reference_titles(refs)
        return [
            {**r, "title": str(titles.get(ref) or r["source_id"])}
            for r, ref in zip(rows, refs, strict=True)
        ]

    @staticmethod
    @grunt.whitelist()
    async def get_delete_impact(
        doctype: str,
        doc_id: str | None = None,
        doc_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Summarise what references the given document(s) - see LinkService."""
        from grunt.permissions.guards import doc_guard

        ids = list(doc_ids) if doc_ids else ([doc_id] if doc_id else [])
        for one in ids:
            await doc_guard(doctype, one)  # permission check per id

        from grunt.document.links import link_service

        return await link_service.get_delete_impact(grunt.get_session(), doctype, ids)

    @staticmethod
    @grunt.whitelist()
    async def get_preview(doctype: str, doc_id: str) -> dict[str, Any] | None:
        """Link hover card: title, image and the ``in_preview`` fields of a document.

        ``None`` when the DocType has ``show_preview_popup`` off or the reader
        can't see the document. Without ``in_preview`` fields the required
        ones are shown instead (as Frappe does).
        """
        meta = await grunt.get_meta(doctype)
        if meta is None or not meta.doc.show_preview_popup:
            return None

        physical = [f for f in meta.get_physical_fields() if f.fieldtype != "Password"]
        fields = [f for f in physical if f.in_preview] or [f for f in physical if f.required]
        title_field = meta.get_title_field()
        image_field = meta.get_image_field()
        fieldnames = {"name", title_field, *(f.fieldname for f in fields)}
        if image_field:
            fieldnames.add(image_field)

        rows = await _optional(
            grunt.get_list(
                doctype,
                filters={"name": doc_id},
                fields=sorted(fieldnames),
                limit=1,
                include_total=False,
            ),
            [],
        )
        if not rows:
            return None
        row = dict(rows[0])
        return {
            "name": str(row.get("name") or doc_id),
            "title": str(row.get(title_field) or doc_id),
            "image": row.get(image_field) if image_field else None,
            "row": row,
            "fields": [
                {
                    "fieldname": f.fieldname,
                    "label": _(f.label or f.fieldname),
                    "fieldtype": f.fieldtype,
                    "options": f.options,
                }
                for f in fields
                if f.fieldname not in (title_field, image_field)
            ],
        }

    @staticmethod
    @grunt.whitelist()
    async def get_sidebar(doctype: str, doc_id: str) -> dict[str, Any]:
        """Return the whole document-sidebar payload in one round-trip.

        Bundles assignees, shares, tags and the current user's
        bookmark so the desk sidebar needs a single request instead of one
        per section.
        """

        doc = await grunt.get_doc(doctype, doc_id, expand=[])  # also the permission check

        ref = {"reference_doctype": doctype, "reference_id": doc_id}

        # Auxiliary sections - independent of each other and of the doc load
        # above, but all run on the one request-scoped AsyncSession, which
        # SQLAlchemy does not allow to be driven from concurrent coroutines
        # (asyncio.gather here would race two queries onto the same session
        # and raise IllegalStateChangeError under load) - so fetch them one
        # at a time. A viewer who can't read one of these system DocTypes
        # just gets an empty section, not a broken sidebar. None of these
        # need pagination totals, so include_total is off to skip the extra
        # COUNT(*) per section.
        assignees = await _optional(
            grunt.get_list(
                "ToDo",
                filters={**ref, "status__in": ["Open", "In Progress"]},
                order_by="created_at",
                order="asc",
                limit=100,
                include_total=False,
            ),
            [],
        )
        shares = await _optional(
            grunt.get_list(
                "SharedWith",
                filters=ref,
                order_by="created_at",
                order="asc",
                limit=100,
                include_total=False,
            ),
            [],
        )
        tags = await _optional(
            grunt.get_list(
                "DocTag",
                filters=ref,
                order_by="created_at",
                order="asc",
                limit=100,
                include_total=False,
            ),
            [],
        )
        bookmarks = await _optional(
            grunt.get_list(
                "Bookmark",
                filters={**ref, "owner": grunt.get_user().email},
                limit=1,
                include_total=False,
            ),
            [],
        )

        follows = await _optional(
            grunt.get_list(
                "DocFollow",
                filters={**ref, "user": grunt.get_user().email},
                limit=1,
                include_total=False,
            ),
            [],
        )

        from grunt.activity.milestones import history as milestone_history

        milestones = await _optional(milestone_history(doctype, doc_id), [])

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
            from grunt.auth.doctypes.User.user import get_users_by_emails

            users = await get_users_by_emails(list(emails), fields=["email", "full_name", "avatar"])
            for u in users:
                email = u.email
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
            "tags": [{"name": str(r["name"]), "tag": r.get("tag")} for r in tags],
            "bookmark": bookmark,
            "follow": {"name": str(follows[0]["name"])} if follows else None,
            "people": people,
            "milestones": [
                {
                    "name": str(m["name"]),
                    "field": m.get("track_field"),
                    "value": m.get("value"),
                    "entered_at": _iso(m.get("entered_at")),
                    "left_at": _iso(m.get("left_at")),
                    "duration_hours": m.get("duration_hours"),
                    "approximate": bool(m.get("approximate")),
                }
                for m in milestones
            ],
        }
