"""Document versioning — stores JSON diffs for every document update.

Each version records which fields changed, their old and new values,
and supports restoring a document to any previous version.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Fields that should not be tracked in version diffs
_SKIP_FIELDS = frozenset({"modified_at", "modified_by"})


class VersionService:
    """Creates and queries version history for documents."""

    async def create_version(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
        old_doc: dict[str, Any],
        new_doc: dict[str, Any],
        user: str,
    ) -> str | None:
        """Create a version record if there are actual changes.

        Args:
            session: DB session.
            doctype: DocType name.
            doc_id: Document ID.
            old_doc: Document data before update.
            new_doc: Document data after update.
            user: Email of the user who made the change.

        Returns:
            Version ID if created, None if no changes detected.
        """
        changes = self._compute_diff(old_doc, new_doc)
        if not changes:
            return None

        from grunt.core.db.system_tables import GruntDocVersion  # noqa: PLC0415

        # Get next version number
        stmt = (
            select(func.coalesce(func.max(GruntDocVersion.version), 0))
            .where(GruntDocVersion.doctype == doctype)
            .where(GruntDocVersion.doc_id == doc_id)
        )
        result = await session.execute(stmt)
        max_version = result.scalar() or 0
        next_version = max_version + 1

        version_id = str(uuid.uuid4())
        version = GruntDocVersion(
            id=version_id,
            doctype=doctype,
            doc_id=doc_id,
            version=next_version,
            changes=changes,
            user=user,
            created_at=datetime.now(timezone.utc),
        )
        session.add(version)
        await session.flush()

        logger.info(
            "version.created",
            doctype=doctype,
            doc_id=doc_id,
            version=next_version,
            fields_changed=len(changes),
        )
        return version_id

    async def get_versions(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
    ) -> list[dict[str, Any]]:
        """Get all versions for a document, newest first."""
        from grunt.core.db.system_tables import GruntDocVersion  # noqa: PLC0415

        stmt = (
            select(GruntDocVersion)
            .where(GruntDocVersion.doctype == doctype)
            .where(GruntDocVersion.doc_id == doc_id)
            .order_by(GruntDocVersion.version.desc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "id": row.id,
                "version": row.version,
                "changes": row.changes,
                "user": row.user,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def get_version(
        self,
        session: AsyncSession,
        version_id: str,
    ) -> dict[str, Any] | None:
        """Get a specific version by ID."""
        from grunt.core.db.system_tables import GruntDocVersion  # noqa: PLC0415

        stmt = select(GruntDocVersion).where(GruntDocVersion.id == version_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        return {
            "id": row.id,
            "doctype": row.doctype,
            "doc_id": row.doc_id,
            "version": row.version,
            "changes": row.changes,
            "user": row.user,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def build_restore_data(
        self,
        current_doc: dict[str, Any],
        versions: list[dict[str, Any]],
        target_version: int,
    ) -> dict[str, Any]:
        """Build the document data as it was at a given version.

        Applies reverse diffs from the current state back to the target version.

        Args:
            current_doc: Current document data.
            versions: All versions, newest first.
            target_version: The version number to restore to.

        Returns:
            Document data at the target version.
        """
        doc = dict(current_doc)

        # Sort versions descending — we undo from newest to target
        for v in sorted(versions, key=lambda x: x["version"], reverse=True):
            if v["version"] <= target_version:
                break
            # Undo this version's changes
            for change in v["changes"]:
                field = change["field"]
                doc[field] = change["old"]

        return doc

    def _compute_diff(
        self,
        old_doc: dict[str, Any],
        new_doc: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Compute field-level diff between two document states.

        Returns a list of {"field": str, "old": Any, "new": Any} dicts.
        """
        changes: list[dict[str, Any]] = []

        all_keys = set(old_doc.keys()) | set(new_doc.keys())
        for key in sorted(all_keys):
            if key in _SKIP_FIELDS:
                continue
            old_val = old_doc.get(key)
            new_val = new_doc.get(key)
            if old_val != new_val:
                changes.append({
                    "field": key,
                    "old": self._serialize(old_val),
                    "new": self._serialize(new_val),
                })

        return changes

    @staticmethod
    def _serialize(value: Any) -> Any:
        """Serialize a value for JSON storage."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            return None
        return value


version_service = VersionService()
