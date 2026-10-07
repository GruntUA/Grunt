"""Read side of the table storage: ``Document.load_from_db``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import select

from grunt import _

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.document.multi_link import MultiLinkService


from grunt.document.formula import evaluate_read_formulas
from grunt.document.mixins.lifecycle import DocumentLifecycleMixin
from grunt.document.relations import _load_child_tables, attach_multi_link_values
from grunt.document.serde import serialize_datetimes


class DocumentReadMixin(DocumentLifecycleMixin):
    doctype: str
    data: dict[str, Any]
    user: Any
    session: AsyncSession
    engine: Any
    _ml: MultiLinkService
    _dt: Any

    # Storage

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        """Read the row with its child tables and MultiLink values into ``self.data``."""
        dt = self._dt
        doc_id = self.data.get("name")
        table = dt.table

        # Singleton - there is only ever one row; ``doc_id`` is irrelevant
        # (callers may pass the doctype name, or nothing at all).
        if dt.is_singleton:
            query = select(table).limit(1)
        else:
            query = select(table).where(table.c.name == doc_id)

        result = await self.session.execute(query)
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("Document “%(name)s” not found") % {"name": doc_id or dt.name},
            )

        doc = serialize_datetimes(dict(row._mapping))

        table_fields = dt.get_table_fieldnames()
        ml_fields = {f.fieldname for f in dt.get_multilink_fields()}

        expand_set = {x for x in (expand or []) if x}
        load_all_relations = expand is None or "*" in expand_set

        # Attach child table values
        if load_all_relations or table_fields:
            selected_tables = None if load_all_relations else (table_fields & expand_set)
            if selected_tables:
                await _load_child_tables(self.session, dt.doc, doc, include_fields=selected_tables)
            elif load_all_relations:
                await _load_child_tables(self.session, dt.doc, doc)

        # Attach MultiLink values
        if ml_fields:
            selected_ml = None if load_all_relations else (ml_fields & expand_set)
            if load_all_relations or selected_ml:
                await attach_multi_link_values(
                    self._ml, dt.name, doc["name"], dt.doc, doc, fields=selected_ml
                )

        # expand=[] means the caller wants the bare row only (e.g. a
        # permission check) - skip read_formula evaluation, which can run
        # arbitrary queries (grunt.count/grunt.get_list) per field.
        if expand is None or expand_set:
            await evaluate_read_formulas(dt.doc, doc)

        self.data = doc
