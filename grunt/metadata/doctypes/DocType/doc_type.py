"""DocType controller - definitions live in the DocType table (JSON ``definition``).

List and count query that table directly; single documents are read from
and written through the registry, which validates and syncs physical tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

import grunt
from grunt.metadata import store
from grunt.metadata.compiler import get_table_name, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.metadata.scaffold import export_doctype_files
from grunt.metadata.virtual import VirtualDocType


def _row_to_doc(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a DocType table row to DocType model data."""
    data: dict[str, Any] = dict(row.get(store.DEFINITION) or {})
    data["name"] = row["name"]
    # Show the resolved physical table name (override, or the computed default)
    # so the read-only "Назва таблиці" field isn't a dead empty box in the form.
    # Virtual DocTypes have no table of their own - leave it blank.
    if not data.get("is_virtual"):
        data["table_name"] = data.get("table_name") or get_table_name(data["module"], row["name"])
    created_at = row.get("created_at")
    modified_at = row.get("modified_at")
    data["created_at"] = created_at.isoformat() if created_at else None
    data["modified_at"] = modified_at.isoformat() if modified_at else None
    return data


def _drop_default_table_name(dt: DocType) -> None:
    """Don't persist ``table_name`` when it just equals the computed default -
    it's surfaced read-only in the form and would round-trip back as a
    spurious override that goes stale if the DocType is ever renamed."""
    if dt.table_name and dt.table_name == get_table_name(dt.module, dt.name):
        dt.table_name = None


class DocTypeController(VirtualDocType):
    lists_from_table = True

    def _session(self):
        return grunt.get_session()

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        row = await store.get_row(self._session(), doc_id)
        return _row_to_doc(row) if row else {}

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Create a new DocType."""
        dt = DocType(**data)
        _drop_default_table_name(dt)
        session = self._session()
        engine = grunt.get_engine()

        if await doctype_registry.get_or_none(dt.name) is not None:
            raise ValueError(f"DocType '{dt.name}' already exists")

        await doctype_registry.register(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files if applicable
        export_doctype_files(dt, app_name=dt.app or None)

        return dt.model_dump()

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Update an existing DocType."""
        dt = DocType(**data)
        _drop_default_table_name(dt)
        session = self._session()
        engine = grunt.get_engine()

        await doctype_registry.update(dt, session, engine)

        # Sync physical table if not virtual/child
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)

        # Export to files
        export_doctype_files(dt, app_name=dt.app or None)

        return dt.model_dump()

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        """Delete a DocType."""
        await doctype_registry.delete(doc_id, self._session())
