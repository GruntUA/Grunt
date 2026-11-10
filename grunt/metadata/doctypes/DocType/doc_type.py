"""DocType controller - definitions live in the DocType table (JSON ``definition``).

List and count query that table directly; single documents are read from
and written through the registry, which validates and syncs physical tables.
"""

from collections.abc import Mapping
from typing import Any

from grunt.document.base import Document
from grunt.local import require_engine
from grunt.metadata import store
from grunt.metadata.compiler import get_table_name, sync_table
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.metadata.scaffold import export_doctype_files
from grunt.store import AGGREGATE, DELETE, INSERT, SQL, UPDATE, SqlStore, Store


def _row_to_doc(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a DocType table row to DocType model data."""
    data: dict[str, Any] = dict(row.get(store.DEFINITION) or {})
    data["name"] = row["name"]
    # Show the resolved physical table name (override, or the computed default)
    # so the read-only "Назва таблиці" field isn't a dead empty box in the form.
    # Virtual DocTypes have no table of their own - leave it blank.
    if data.get("storage", "sql") == "sql":
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


class DocTypeStore(SqlStore):
    """Definitions are rows of the DocType table: lists and counts query it like
    any table; a single definition is read from the row's JSON and written
    through the registry, which validates it and syncs its physical table."""

    capabilities = frozenset({INSERT, UPDATE, DELETE, AGGREGATE, SQL})

    @property
    def columns(self) -> frozenset[str] | None:
        return None  # a definition holds any property the model takes

    async def get(self, name: str, *, expand: list[str] | None = None) -> dict[str, Any] | None:
        row = await store.get_row(self.session, name)
        return None if row is None else _row_to_doc(row)

    async def insert(
        self, doc: dict[str, Any], *, input: dict[str, Any], user: str
    ) -> dict[str, Any]:
        """Register the new DocType, create its table and export its files."""
        dt = DocType(**doc)
        _drop_default_table_name(dt)
        engine = require_engine()
        if await doctype_registry.get_or_none(dt.name) is not None:
            raise ValueError(f"DocType '{dt.name}' already exists")
        await doctype_registry.register(dt, self.session, engine)
        if dt.has_table and not dt.is_child:
            await sync_table(dt, engine, session=self.session)
        export_doctype_files(dt, app_name=dt.app or None)
        return dt.model_dump()

    async def update(
        self,
        name: str,
        doc: dict[str, Any],
        *,
        before: dict[str, Any],
        input: dict[str, Any],
        user: str,
    ) -> dict[str, Any]:
        """Update the DocType, sync its table and export its files."""
        dt = DocType(**doc)
        _drop_default_table_name(dt)
        engine = require_engine()
        await doctype_registry.update(dt, self.session, engine)
        if dt.has_table and not dt.is_child:
            await sync_table(dt, engine, session=self.session)
        export_doctype_files(dt, app_name=dt.app or None)
        return await self.output(dt.model_dump())

    async def delete(self, name: str, *, before: dict[str, Any]) -> None:
        await doctype_registry.delete(name, self.session)

    async def output(self, doc: dict[str, Any]) -> dict[str, Any]:
        return await Store.output(self, doc)


class DocTypeController(Document):
    """The controller of DocType definitions - stored by :class:`DocTypeStore`."""

    # The class can't be named DocType (that's the metadata model imported
    # above), so documents.get_doc(DocTypeController, ...) takes the name from here.
    doctype = "DocType"
    store_class = DocTypeStore
