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


class DocumentHistoryRPCMixin:
    """Version history / activity log / timeline, exposed via the RPC dispatcher."""

    @staticmethod
    @grunt.whitelist()
    async def get_versions(doctype: str, doc_id: str) -> list[dict[str, Any]]:
        """Return version history for a document."""
        from grunt.app import grunt as grunt_app

        # Ensure document exists and user has access
        await grunt_app.get_doc(doctype, doc_id)

        from grunt.document.versioning import version_service

        return await version_service.get_versions(grunt_app._require_session(), doctype, doc_id)

    @staticmethod
    @grunt.whitelist()
    async def restore_version(doctype: str, doc_id: str, version_id: str) -> dict[str, Any]:
        """Restore a document to a previous version."""
        from grunt.app import grunt as grunt_app
        from grunt.document.versioning import version_service

        # Get current doc and verify access
        current_doc = await grunt_app.get_doc(doctype, doc_id)

        session = grunt_app._require_session()
        target = await version_service.get_version(session, version_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Версію не знайдено")
        if target["doctype"] != doctype or target["doc_id"] != doc_id:
            raise HTTPException(status_code=400, detail="Версія не належить цьому документу")

        # Get all versions for this doc
        all_versions = await version_service.get_versions(session, doctype, doc_id)

        # Build restore data
        restore_data = version_service.build_restore_data(
            current_doc, all_versions, target["version"]
        )

        # Apply as a regular update
        meta = await grunt_app.get_meta(doctype)

        update_fields = {}
        for field in meta.get_physical_fields():
            if field.fieldname in restore_data:
                update_fields[field.fieldname] = restore_data[field.fieldname]

        result = await grunt_app.save_doc(doctype, doc_id, update_fields)

        # Add audit log — via the shared write path (grunt.activity.record_activity),
        # not a raw grunt.new_doc("ActivityLog", ...) call: ActivityLog.create is
        # restricted to System Manager to keep the audit trail tamper-proof, and
        # record_activity is the one path that's allowed to write as any user.
        from grunt.activity import record_activity

        await record_activity(
            doctype,
            doc_id,
            "restore",
            user_email=grunt_app.session.user,
            details={"to_version": target["version"]},
        )

        return {"document": result, "restored_to_version": target["version"]}

    @staticmethod
    @grunt.whitelist()
    async def get_activity_log(
        doctype: str, doc_id: str, per_page: int = 10
    ) -> list[dict[str, Any]]:
        """Return the activity log for a document."""
        from grunt.app import grunt as grunt_app

        await grunt_app.get_doc(doctype, doc_id)

        per_page = max(1, min(per_page, 100))

        entries = await grunt_app.get_list(
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
        """Return a merged timeline of activity and comments."""
        from grunt.app import grunt as grunt_app

        await grunt_app.get_doc(doctype, doc_id, expand=[])  # permission check only

        act_rows = await grunt_app.get_list(
            "ActivityLog", filters={"doctype": doctype, "doc_id": doc_id}, limit=1000
        )

        comment_rows = await grunt_app.get_list(
            "Comment", filters={"reference_doctype": doctype, "reference_id": doc_id}, limit=1000
        )

        items: list[dict[str, Any]] = []
        for r in act_rows:
            items.append(
                {
                    "type": "activity",
                    "name": str(r["name"]),
                    "action": r.get("action"),
                    "user": r.get("user"),
                    "details": r.get("details"),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
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

        items.sort(key=lambda x: x["created_at"] or "")
        return items
