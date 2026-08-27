"""Read-side mixin for the Document pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.document.multi_link import MultiLinkService


from grunt.document.formula import evaluate_read_formulas
from grunt.document.meta import Meta
from grunt.document.relations import _load_child_tables, attach_multi_link_values
from grunt.document.serde import serialize_datetimes
from grunt.document.virtual import is_virtual_routed, virtual_get
from grunt.metadata.registry import doctype_registry


class DocumentReadMixin:
    session: AsyncSession
    _ml: MultiLinkService

    # ── Get ────────────────────────────────────────────────────────────

    async def get_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: User,
        expand: list[str] | None = None,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if is_virtual_routed(dt, doctype_name):
            return await virtual_get(doctype_name, user, doc_id)

        meta = Meta(dt)
        table = meta.table

        result = await self.session.execute(select(table).where(table.c.name == doc_id))
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found.",
            )

        doc = serialize_datetimes(dict(row._mapping))

        table_fields = meta.get_table_fieldnames()
        ml_fields = {f.fieldname for f in meta.get_multilink_fields()}

        expand_set = {x for x in (expand or []) if x}
        load_all_relations = expand is None or "*" in expand_set

        # Attach child table values
        if load_all_relations or table_fields:
            selected_tables = None if load_all_relations else (table_fields & expand_set)
            if selected_tables:
                await _load_child_tables(self.session, dt, doc, include_fields=selected_tables)
            elif load_all_relations:
                await _load_child_tables(self.session, dt, doc)

        # Attach MultiLink values
        if ml_fields:
            selected_ml = None if load_all_relations else (ml_fields & expand_set)
            if load_all_relations or selected_ml:
                await attach_multi_link_values(
                    self._ml, doctype_name, doc["name"], dt, doc, fields=selected_ml
                )

        await evaluate_read_formulas(dt, doc)

        # Call controller on_load if the app overrides it
        from grunt.document.base import Document
        from grunt.document.registry import document_registry

        controller_cls = document_registry.get(doctype_name)
        if controller_cls.on_load is not Document.on_load:
            controller = controller_cls(doctype_name, doc, user, self.session)
            await controller.on_load()

        return doc
