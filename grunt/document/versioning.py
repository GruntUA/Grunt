"""Document versioning — stores JSON diffs for every document update.

Each version records which fields changed, their old and new values,
and supports restoring a document to any previous version.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from grunt import _, log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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

        import grunt

        dt_version = await grunt.get_meta("DocVersion")
        if dt_version is None:
            from grunt.errors import not_found

            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "DocVersion"})
        table = dt_version.table

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

        log.info(
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
        import grunt

        dt_version = await grunt.get_meta("DocVersion")
        if dt_version is None:
            from grunt.errors import not_found

            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "DocVersion"})
        table = dt_version.table
        stmt = (
            select(table)
            .where(table.c.doctype == doctype)
            .where(table.c.doc_id == doc_id)
            .order_by(table.c.version.desc())
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()

        versions = [
            {
                "id": row["name"],
                "version": row["version"],
                "changes": row["changes"],
                "user": row["user"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

        dt = await grunt.get_meta(doctype)
        if dt is not None:
            await self.resolve_change_labels(session, dt, versions)

        return versions

    async def resolve_change_labels(
        self,
        session: AsyncSession,
        dt: Any,
        versions: list[dict[str, Any]],
    ) -> None:
        """Add ``old_label``/``new_label`` to Link-field changes, in place.

        Lets version diffs show a linked record's display title (e.g. an
        Employee's name) instead of its raw id — mirrors the ``__label``
        Link resolution already done for regular document reads
        (see ``grunt.document.relations``).
        """
        link_fields = {
            f.fieldname: f for f in dt.get_link_fields() if f.fieldtype == "Link" and f.options
        }
        if not link_fields:
            return

        ids_by_target: dict[str, set[str]] = {}
        for v in versions:
            for change in v.get("changes") or []:
                field = link_fields.get(change.get("field"))
                if field is None:
                    continue
                for key in ("old", "new"):
                    val = change.get(key)
                    if val not in (None, ""):
                        ids_by_target.setdefault(field.options, set()).add(str(val))

        if not ids_by_target:
            return

        from grunt.document.meta import Meta
        from grunt.metadata.registry import doctype_registry

        label_maps: dict[str, dict[str, str]] = {}
        for target_name, ids in ids_by_target.items():
            try:
                target_dt = await doctype_registry.get(target_name)
            except Exception:
                log.warning("version.link_label_target_error", target=target_name)
                continue
            target_meta = Meta(target_dt)
            title_field = target_meta.get_title_field()
            target_table = target_meta.table
            cols = [target_table.c.name]
            if title_field != "name" and title_field in target_table.c:
                cols.append(target_table.c[title_field])
            try:
                async with session.begin_nested():
                    result = await session.execute(
                        select(*cols).where(target_table.c.name.in_(ids))
                    )
                    rows = result.mappings().all()
            except Exception:
                log.warning("version.link_label_fetch_error", target=target_name)
                continue
            label_maps[target_name] = {
                str(r["name"]): str(r.get(title_field) or r["name"]) for r in rows
            }

        for v in versions:
            for change in v.get("changes") or []:
                field = link_fields.get(change.get("field"))
                if field is None:
                    continue
                label_map = label_maps.get(field.options, {})
                if change.get("old") not in (None, ""):
                    change["old_label"] = label_map.get(str(change["old"]), str(change["old"]))
                if change.get("new") not in (None, ""):
                    change["new_label"] = label_map.get(str(change["new"]), str(change["new"]))

    async def get_version(
        self,
        session: AsyncSession,
        version_id: str,
    ) -> dict[str, Any] | None:
        """Get a specific version by ID."""
        import grunt

        dt_version = await grunt.get_meta("DocVersion")
        if dt_version is None:
            from grunt.errors import not_found

            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "DocVersion"})
        table = dt_version.table
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
        """Serialize a value for JSON storage (recurses into list/dict)."""
        from datetime import date, datetime

        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            return None
        if isinstance(value, list):
            return [VersionService._serialize(v) for v in value]
        if isinstance(value, dict):
            return {k: VersionService._serialize(v) for k, v in value.items()}
        return value


version_service = VersionService()
