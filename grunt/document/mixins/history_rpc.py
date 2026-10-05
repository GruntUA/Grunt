"""History/Activity RPC methods, exposed as static methods of ``Document``.

RPC: grunt.document.base.Document.get_versions
RPC: grunt.document.base.Document.restore_version
RPC: grunt.document.base.Document.get_activity_log
RPC: grunt.document.base.Document.get_timeline
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

import grunt
from grunt import _
from grunt.activity import record_activity
from grunt.document.versioning import version_service
from grunt.errors import not_found
from grunt.permissions.guards import doc_guard


class DocumentHistoryRPCMixin:
    """Version history / activity log / timeline, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_versions(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return version history for a document."""
        # Ensure document exists and user has access
        await doc_guard(doctype, doc_id)

        return await version_service.get_versions(grunt.get_session(), doctype, doc_id)

    @staticmethod
    @grunt.whitelist()
    async def restore_version(doctype: str, doc_id: str, version_id: str) -> dict[str, Any]:
        """Restore a document to a previous version."""
        # Get current doc and verify access
        current_doc = await grunt.get_doc(doctype, doc_id)

        session = grunt.get_session()
        target = await version_service.get_version(session, version_id)
        if target is None:
            raise HTTPException(status_code=404, detail=_("Version not found"))
        if target["doctype"] != doctype or target["doc_id"] != doc_id:
            raise HTTPException(
                status_code=400, detail=_("The version does not belong to this document")
            )

        # Get all versions for this doc
        all_versions = await version_service.get_versions(session, doctype, doc_id)

        # Build restore data
        restore_data = version_service.build_restore_data(
            current_doc, all_versions, target["version"]
        )

        # Apply as a regular update

        meta = await grunt.get_meta(doctype)
        if meta is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})

        update_fields = {}
        for field in meta.get_physical_fields():
            if field.fieldname in restore_data:
                update_fields[field.fieldname] = restore_data[field.fieldname]

        result = await grunt.save_doc(doctype, doc_id, update_fields)

        # Add audit log - via the shared write path (grunt.activity.record_activity),
        # not a raw grunt.new_doc("ActivityLog", ...) call: ActivityLog.create is
        # restricted to System Manager to keep the audit trail tamper-proof, and
        # record_activity is the one path that's allowed to write as any user.

        await record_activity(
            doctype,
            doc_id,
            "restore",
            user_email=grunt.get_user().email,
            details={"to_version": target["version"]},
        )

        return {"document": result, "restored_to_version": target["version"]}

    @staticmethod
    @grunt.whitelist()
    async def get_activity_log(
        doctype: str, doc_id: str, per_page: int = 10
    ) -> list[dict[str, Any]]:
        """Return the activity log for a document."""
        await doc_guard(doctype, doc_id)

        per_page = max(1, min(per_page, 100))

        entries = await grunt.get_list(
            "ActivityLog",
            filters={"doctype": doctype, "doc_id": doc_id},
            order_by="created_at",
            order="desc",
            limit=per_page,
        )

        return [
            {
                "name": str(e["name"]),
                "action": e.get("action"),
                "user": e.get("user"),
                "details": e.get("details"),
                "created_at": str(e["created_at"]) if e.get("created_at") else None,
            }
            for e in entries
        ]

    @staticmethod
    @grunt.whitelist()
    async def get_timeline(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return a merged timeline of activity, field-value versions and comments."""
        await doc_guard(doctype, doc_id)

        dt = await grunt.get_meta(doctype)
        track_changes = bool(dt and dt.track_changes)

        act_rows = await grunt.get_list(
            "ActivityLog", filters={"doctype": doctype, "doc_id": doc_id}, limit=1000
        )

        comment_rows = await grunt.get_list(
            "Comment", filters={"reference_doctype": doctype, "reference_id": doc_id}, limit=1000
        )

        items: list[dict[str, Any]] = []
        for r in act_rows:
            action = r.get("action")
            # When versions are tracked, each "Update" is reported as a richer
            # "version" item below (with the actual old/new values) - skip the
            # plain field-name-only entry to avoid showing the same edit twice.
            if track_changes and action in ("Update", "update"):
                continue
            items.append(
                {
                    "type": "activity",
                    "name": str(r["name"]),
                    "action": action,
                    "user": r.get("user"),
                    "details": r.get("details"),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
                }
            )

        if track_changes:
            from grunt.document.versioning import version_service

            versions = await version_service.get_versions(grunt.get_session(), doctype, doc_id)
            for v in versions:
                items.append(
                    {
                        "type": "version",
                        "name": v["id"],
                        "version": v["version"],
                        "changes": v["changes"],
                        "user": v["user"],
                        "created_at": v["created_at"],
                    }
                )

        for r in comment_rows:
            items.append(
                {
                    "type": "comment",
                    "name": str(r["name"]),
                    "content": r.get("content"),
                    "comment_type": r.get("comment_type"),
                    "user": r.get("owner"),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
                }
            )

        # Display names/avatars of the authors, so the UI needn't list all users.
        emails = {i["user"] for i in items if i.get("user")}
        if emails:
            from grunt.auth.doctypes.User.user import get_users_by_emails

            users = await get_users_by_emails(list(emails), fields=["email", "full_name", "avatar"])
            people = {u.email: (getattr(u, "full_name", None), u.data.get("avatar")) for u in users}
            for i in items:
                name, avatar = people.get(i.get("user"), (None, None))
                i["user_name"] = name or None
                i["user_avatar"] = avatar or None

        items.sort(key=lambda x: x["created_at"] or "")
        return items
