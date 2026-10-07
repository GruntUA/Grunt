"""Write side of the table storage: ``Document``'s steps of the pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from grunt import _
from grunt.document.aggregate import compute_aggregations
from grunt.document.formula import compute_formulas
from grunt.document.mixins.lifecycle import PROTECTED_FIELDS
from grunt.document.mixins.read import DocumentReadMixin
from grunt.document.relations import (
    _load_child_tables,
    _save_child_tables,
    attach_multi_link_values,
)
from grunt.document.serde import serialize_datetimes
from grunt.document.update_side_effects import (
    delete_row_and_links,
    fire_delete_services,
    fire_update_services,
    record_update_changes,
)
from grunt.search.service import search_index_service
from grunt.webhook.service import webhook_service
from grunt.website.generator import fill_route

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


class DocumentWriteMixin(DocumentReadMixin):
    """Writes of the table storage, and the table's steps of the pipeline.

    Extends :class:`DocumentReadMixin` for the table reads the steps share.
    """

    engine: AsyncEngine
    _submitted: dict[str, Any]
    _existing: dict[str, Any] | None

    # Storage

    async def db_insert(self) -> None:
        """INSERT ``self.data`` with its child tables, aggregates and MultiLink values.

        Child-table rows and MultiLink lists are taken from the submitted values.
        """
        dt = self._dt
        table = dt.table
        row = self.data
        data = self._submitted
        doc_id = row["name"]
        db_row = {k: v for k, v in row.items() if k in table.c}
        await self.session.execute(table.insert().values(**db_row))
        # Flush so the parent row exists before the child rows reference it.
        await self.session.flush()
        now = row.get("created_at") or datetime.now(UTC)
        await _save_child_tables(self.session, dt.doc, doc_id, data, self.user, now)
        await self._apply_aggregations(dt, table, doc_id, row)
        await self._sync_multi_links(dt, doc_id, data)

    async def db_update(self) -> None:
        """UPDATE the row to ``self.data``, then child tables, aggregates and MultiLink.

        Formulas are computed on ``self.data`` (the post-hook merged doc) and then a
        single pass copies every physical field that differs from the stored row
        into the UPDATE. This captures both lifecycle-hook mutations and freshly
        computed formula values in one place before the UPDATE is issued.
        """
        dt = self._dt
        table = dt.table
        row = self.data
        existing = self._existing or {}
        real_id = existing["name"]
        await compute_formulas(dt.doc, row)

        update_data = self._build_update_payload(dt, self._submitted)
        table_cols = {c.name for c in table.columns}
        for field in dt.get_physical_fields():
            if field.fieldname in PROTECTED_FIELDS or field.fieldname not in table_cols:
                continue
            if row.get(field.fieldname) != existing.get(field.fieldname):
                update_data[field.fieldname] = row[field.fieldname]
        # The audit stamps of the merged doc, not fresh ones.
        for key in ("modified_at", "modified_by"):
            if key in update_data:
                update_data[key] = row[key]

        await self.session.execute(
            table.update().where(table.c.name == real_id).values(**update_data)
        )

        await _save_child_tables(self.session, dt.doc, real_id, row, self.user, datetime.now(UTC))
        await self._apply_aggregations(dt, table, real_id, row)

        await self._sync_multi_links(dt, real_id, self._submitted, only_present=True)

        await self.session.flush()

    async def db_delete(self) -> None:
        """DELETE the row and its MultiLink relations."""
        await delete_row_and_links(
            session=self.session,
            ml=self._ml,
            table=self._dt.table,
            doctype_name=self.doctype,
            real_id=self.data["name"],
        )

    async def _apply_aggregations(
        self,
        dt: Any,
        table: Any,
        doc_id: str,
        row: dict[str, Any],
    ) -> None:
        """Compute and persist aggregate fields derived from child tables."""
        agg_values = await compute_aggregations(self.session, dt.doc, doc_id)
        if not agg_values:
            return

        await self.session.execute(
            table.update().where(table.c.name == doc_id).values(**agg_values)
        )
        row.update(agg_values)
        await self.session.flush()

    async def _sync_multi_links(
        self,
        dt: Any,
        doc_id: str,
        data: dict[str, Any],
        *,
        only_present: bool = False,
    ) -> None:
        """Persist values for MultiLink virtual relation fields.

        With ``only_present=True`` fields absent from *data* are left untouched
        (used on update so unmentioned relations are preserved).
        """
        for mlf in dt.get_multilink_fields():
            if only_present and mlf.fieldname not in data:
                continue
            values = data.get(mlf.fieldname)
            if isinstance(values, list):
                await self._ml.set_values(
                    self.doctype,
                    doc_id,
                    mlf.fieldname,
                    mlf.options or "",
                    values,
                )

    # Pipeline steps

    def _columns(self, dt: Any) -> set[str] | None:
        return {c.name for c in dt.table.columns}

    async def _check_can_insert(self, dt: Any) -> None:
        """Raise 409 if the DocType is a singleton and a document already exists."""
        if not dt.is_singleton:
            return
        if await self._singleton_rows(dt) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("'%(name)s' is a singleton.") % {"name": dt.name},
            )

    async def _insert_instead_of_update(self, dt: Any) -> bool:
        return dt.is_singleton and await self._singleton_rows(dt) == 0

    async def _singleton_rows(self, dt: Any) -> int:
        result = await self.session.execute(select(func.count()).select_from(dt.table))
        return result.scalar() or 0

    async def _before_db_write(self, dt: Any, *, insert: bool) -> None:
        await fill_route(dt, self.data, self.session)
        if insert:
            await compute_formulas(dt.doc, self.data)

    async def _output(self, dt: Any, *, reload_children: bool) -> dict[str, Any]:
        """Serialise, (on update) reload child tables, and attach MultiLink values."""
        result = serialize_datetimes(dict(self.data) if reload_children else self.data)
        if reload_children:
            await _load_child_tables(self.session, dt.doc, result)
        await attach_multi_link_values(self._ml, self.doctype, result["name"], dt.doc, result)
        return result

    async def _after_insert(self, dt: Any) -> None:
        """Update the search index and fire outgoing webhooks after a successful insert."""
        await search_index_service.index_document(self.session, self.doctype, dt.doc, self.data)
        await webhook_service.fire(self.session, "after_insert", self.doctype, self.data)

    async def _record_update(self, dt: Any, existing: dict[str, Any], result: dict[str, Any]):
        await record_update_changes(
            session=self.session,
            engine=self.engine,
            doctype_name=self.doctype,
            real_id=existing["name"],
            dt=dt,
            existing=existing,
            result=result,
            user=self.user,
        )

    async def _after_update(self, dt: Any, result: dict[str, Any]) -> None:
        await fire_update_services(
            session=self.session, doctype_name=self.doctype, dt=dt.doc, result=result
        )

    async def _repoint_references(self, dt: Any, real_id: str, replace_with: str) -> None:
        from grunt.document.collection import repoint_references, validate_replacement

        await validate_replacement(self.session, dt, real_id, replace_with)
        try:
            await repoint_references(
                self.session, dt, self.doctype, real_id, replace_with, is_merge=True
            )
            await self.session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_("Could not reassign the links: uniqueness conflict"),
            ) from exc

    async def _after_delete(self, dt: Any, real_id: str, existing: dict[str, Any]) -> None:
        await fire_delete_services(
            session=self.session, doctype_name=self.doctype, real_id=real_id, existing=existing
        )
