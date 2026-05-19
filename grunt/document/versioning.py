"""Document versioning — stores JSON diffs for every document update.

Each version records which fields changed, their old and new values,
and supports restoring a document to any previous version.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select

if TYPE_CHECKING:
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

        from grunt.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["DocVersion"])

        # Get next version number
        stmt = (
            select(func.coalesce(func.max(table.c.version), 0))
            .where(table.c.doctype == doctype)
            .where(table.c.doc_id == doc_id)
        )
        result = await session.execute(stmt)
        max_version = result.scalar() or 0
        next_version = max_version + 1

        version_name = f"{doctype}-{doc_id}-v{next_version}"
        now = datetime.now(UTC)
        await session.execute(
            table.insert().values(
                name=version_name,
                owner=user,
                created_at=now,
                modified_at=now,
                modified_by=user,
                docstatus=0,
                doctype=doctype,
                doc_id=doc_id,
                version=next_version,
                changes=changes,
                user=user,
            )
        )
        await session.flush()

        logger.info(
            "version.created",
            doctype=doctype,
            doc_id=doc_id,
            version=next_version,
            fields_changed=len(changes),
        )
        return version_name

    async def get_versions(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
    ) -> list[dict[str, Any]]:
        """Get all versions for a document, newest first."""
        from grunt.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["DocVersion"])
        stmt = (
            select(table)
            .where(table.c.doctype == doctype)
            .where(table.c.doc_id == doc_id)
            .order_by(table.c.version.desc())
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "id": row["name"],
                "version": row["version"],
                "changes": row["changes"],
                "user": row["user"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

    async def get_version(
        self,
        session: AsyncSession,
        version_id: str,
    ) -> dict[str, Any] | None:
        """Get a specific version by ID."""
        from grunt.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["DocVersion"])
        stmt = select(table).where(table.c.name == version_id)
        result = await session.execute(stmt)
        row = result.mappings().first()
        if row is None:
            return None

        return {
            "id": row["name"],
            "doctype": row["doctype"],
            "doc_id": row["doc_id"],
            "version": row["version"],
            "changes": row["changes"],
            "user": row["user"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
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
                changes.append(
                    {
                        "field": key,
                        "old": self._serialize(old_val),
                        "new": self._serialize(new_val),
                    }
                )

        return changes

    @staticmethod
    def _serialize(value: Any) -> Any:
        """Serialize a value for JSON storage."""
        from datetime import date, datetime  # noqa: PLC0415

        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            return None
        return value


version_service = VersionService()
