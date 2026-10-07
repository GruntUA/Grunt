"""DocType controller - definitions live in the DocType table (JSON ``definition``).

List and count query that table directly; single documents are read from
and written through the registry, which validates and syncs physical tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

import grunt
from grunt import _
from grunt.document.base import BaseDocument, Document, DocumentList
from grunt.errors import not_found
from grunt.metadata import store
from grunt.metadata.compiler import get_table_name, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.metadata.scaffold import export_doctype_files


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


class DocTypeController(BaseDocument):
    """Single DocTypes are read from and written through the registry; lists
    and counts query the DocType table like any table-backed DocType."""

    @classmethod
    async def get_list(cls, doctype: str, **kwargs: Any) -> DocumentList:
        return await Document.get_list(doctype, **kwargs)

    @classmethod
    async def get_count(cls, doctype: str, **kwargs: Any) -> int:
        return await Document.get_count(doctype, **kwargs)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        row = await store.get_row(grunt.get_session(), str(self.name))
        if row is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": self.name})
        self.data = _row_to_doc(row)

    async def db_insert(self) -> None:
        """Register the new DocType, create its table and export its files."""
        dt = DocType(**self.data)
        _drop_default_table_name(dt)
        session = grunt.get_session()
        engine = grunt.get_engine()

        if await doctype_registry.get_or_none(dt.name) is not None:
            raise ValueError(f"DocType '{dt.name}' already exists")

        await doctype_registry.register(dt, session, engine)
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)
        export_doctype_files(dt, app_name=dt.app or None)
        self.data = dt.model_dump()

    async def db_update(self) -> None:
        """Update the DocType, sync its table and export its files."""
        dt = DocType(**self.data)
        _drop_default_table_name(dt)
        session = grunt.get_session()
        engine = grunt.get_engine()

        await doctype_registry.update(dt, session, engine)
        if not dt.is_virtual and not dt.is_child:
            await sync_table(dt, engine, session=session)
        export_doctype_files(dt, app_name=dt.app or None)
        self.data = dt.model_dump()

    async def db_delete(self) -> None:
        await doctype_registry.delete(str(self.name), grunt.get_session())
