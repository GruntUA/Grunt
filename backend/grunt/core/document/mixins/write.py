"""Mixin classes for DocumentService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from itertools import islice
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select, update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.doctypes.user.user import User
    from grunt.core.document.multi_link import MultiLinkService

from grunt.app import GruntError
from grunt.core.document.aggregate import compute_aggregations
from grunt.core.document.formula import compute_formulas
from grunt.core.document.registry import document_registry
from grunt.core.document.relations import (
    _get_multi_link_fields,
    _load_child_tables,
    _save_child_tables,
)
from grunt.core.document.validation import _coerce_value, _validate_data
from grunt.core.document.virtual import (
    _virtual_create,
    _virtual_delete,
    _virtual_update,
)
from grunt.core.document.update_side_effects import (
    bulk_delete_virtual,
    collect_bulk_delete_candidates,
    delete_row_and_links,
    fire_delete_services,
    fire_update_services,
    record_update_changes,
    run_bulk_after_delete_hooks,
    run_bulk_before_delete_hooks,
    run_bulk_delete_writes,
)
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

PROTECTED_FIELDS = frozenset({"id", "owner", "created_at", "docstatus"})


# SQLite degrades with large IN (...) lists; 500 is safe for all backends.
_IN_CHUNK = 500


def _chunks(lst: list, size: int):
    it = iter(lst)
    while chunk := list(islice(it, size)):
        yield chunk


class DocumentWriteMixin:
    session: AsyncSession
    engine: AsyncEngine
    _ml: MultiLinkService

    def _set_grunt_context(self, user: User) -> tuple:  # type: ignore[empty-body]
        ...

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None: ...

    async def get_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: User,
        expand: list[str] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    # ── Create ────────────────────────────────────────────────────────────

    # ── create helpers ────────────────────────────────────────────────────

    async def _check_singleton(self, dt: Any, table: Any) -> None:
        """Raise 409 if the DocType is a singleton and a document already exists."""
        if not dt.is_singleton:
            return
        existing = await self.session.execute(select(func.count()).select_from(table))
        if (existing.scalar() or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"'{dt.name}' is a singleton.",
            )

    async def _build_initial_row(
        self,
        dt: Any,
        table: Any,
        data: dict[str, Any],
        user: User,
        now: datetime,
    ) -> tuple[str, dict[str, Any]]:
        """Assemble the initial DB row dict (standard fields + DocType fields + workflow).

        Returns ``(doc_id, row)``.
        """
        from grunt.core.naming import naming_service  # noqa: PLC0415

        generated_name = await naming_service.generate(dt.autoname or "", data, self.session)
        doc_id = str(data.get("id") or generated_name or uuid.uuid4())

        row: dict[str, Any] = {}
        standard: dict[str, Any] = {
            "id": doc_id,
            "name": generated_name or doc_id[:8],
            "owner": user.email,
            "created_at": now,
            "modified_at": now,
            "modified_by": user.email,
            "docstatus": 0,
        }
        for k, v in standard.items():
            if k in table.c:
                row[k] = v

        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname in data:
                row[field.fieldname] = _coerce_value(data[field.fieldname], field.fieldtype)
            elif field.default is not None:
                row[field.fieldname] = _coerce_value(field.default, field.fieldtype)
            elif field.fieldtype == "Check":
                row[field.fieldname] = False

        if dt.workflow:
            sf = dt.workflow.state_field
            if sf in data:
                row[sf] = data[sf]
            elif sf not in row:
                initial = next((s for s in dt.workflow.states if s.is_initial), None)
                if initial:
                    row[sf] = initial.name

        return doc_id, row

    async def _persist_new_doc(
        self,
        dt: Any,
        table: Any,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        row: dict[str, Any],
        user: User,
        now: datetime,
    ) -> None:
        """Run create pipeline: hooks -> insert -> children -> aggregates -> links -> hooks."""
        controller_cls = document_registry.get(doctype_name)
        doc = controller_cls(doctype_name, row, user, self.session)

        await self._run_create_before_hooks(doc)
        await compute_formulas(dt, row)
        await self._insert_row(table, row)
        await self._save_children(dt, doc_id, data, user, now)
        await self._apply_aggregations(dt, table, doc_id, row)
        await self._sync_multi_links(dt, doctype_name, doc_id, data)

        logger.info("document.created", doctype=doctype_name, id=doc_id)
        await self._run_create_after_hooks(doc)

    async def _run_create_before_hooks(self, doc: Any) -> None:
        """Run validate/before_insert/before_save hooks and normalize hook errors."""
        try:
            await doc.validate()
            await doc.before_insert()
            await doc.before_save()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    async def _insert_row(self, table: Any, row: dict[str, Any]) -> None:
        """Insert main document row and flush to materialize DB state before child writes."""
        await self.session.execute(table.insert().values(**row))
        await self.session.flush()

    async def _save_children(
        self,
        dt: Any,
        doc_id: str,
        data: dict[str, Any],
        user: User,
        now: datetime,
    ) -> None:
        """Persist child-table rows for the created document."""
        await _save_child_tables(self.session, dt, doc_id, data, user, now)

    async def _apply_aggregations(
        self,
        dt: Any,
        table: Any,
        doc_id: str,
        row: dict[str, Any],
    ) -> None:
        """Compute and persist aggregate fields derived from child tables."""
        agg_values = await compute_aggregations(self.session, dt, doc_id)
        if not agg_values:
            return

        await self.session.execute(
            table.update().where(table.c.id == doc_id).values(**agg_values)
        )
        row.update(agg_values)
        await self.session.flush()

    async def _sync_multi_links(
        self,
        dt: Any,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
    ) -> None:
        """Persist values for MultiLink virtual relation fields."""
        for mlf in _get_multi_link_fields(dt):
            values = data.get(mlf.fieldname)
            if isinstance(values, list):
                await self._ml.set_values(
                    doctype_name,
                    doc_id,
                    mlf.fieldname,
                    mlf.options or "",
                    values,
                )

    async def _run_create_after_hooks(self, doc: Any) -> None:
        """Run after_insert/after_save hooks and normalize hook errors."""
        try:
            await doc.after_insert()
            await doc.after_save()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    async def _fire_create_services(
        self, doctype_name: str, dt: Any, row: dict[str, Any]
    ) -> None:
        """Update the search index and fire outgoing webhooks after a successful insert."""
        from grunt.core.search.service import search_index_service  # noqa: PLC0415
        from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

        await search_index_service.index_document(self.session, doctype_name, dt, row)
        await webhook_service.fire(self.session, "after_insert", doctype_name, row)

    async def _serialize_doc_out(
        self, doctype_name: str, doc_id: str, row: dict[str, Any], dt: Any
    ) -> dict[str, Any]:
        """Serialise datetime values and attach MultiLink field values for the response."""
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()
        for mlf in _get_multi_link_fields(dt):
            row[mlf.fieldname] = await self._ml.get_values(doctype_name, doc_id, mlf.fieldname)
        return row

    # ── Create ────────────────────────────────────────────────────────────

    async def create_document(
        self,
        doctype_name: str,
        data: dict[str, Any],
        user: User,
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            return await _virtual_create(doctype_name, user, data)

        table = compile_doctype_to_table(dt)
        await self._check_singleton(dt, table)

        errors = _validate_data(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors
            )

        now = datetime.now(UTC)
        doc_id, row = await self._build_initial_row(dt, table, data, user, now)

        _tokens = self._set_grunt_context(user)
        try:
            await self._persist_new_doc(dt, table, doctype_name, doc_id, data, row, user, now)
            await self._fire_create_services(doctype_name, dt, row)
        finally:
            self._reset_grunt_context(_tokens)

        return await self._serialize_doc_out(doctype_name, doc_id, row, dt)

    # ── update helpers ────────────────────────────────────────────────────

    def _build_update_payload(
        self,
        dt: Any,
        table: Any,
        data: dict[str, Any],
        user: User,
    ) -> dict[str, Any]:
        """Return the dict of fields to write into the DB (stripped + coerced)."""
        table_columns = {c.name for c in table.columns}
        update_data: dict[str, Any] = {}
        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname not in table_columns:
                continue
            if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                update_data[field.fieldname] = _coerce_value(data[field.fieldname], field.fieldtype)
        if "modified_at" in table.c:
            update_data["modified_at"] = datetime.now(UTC)
        if "modified_by" in table.c:
            update_data["modified_by"] = user.email
        return update_data

    @staticmethod
    async def _propagate_formulas(
        dt: Any, merged: dict[str, Any], update_data: dict[str, Any]
    ) -> None:
        """Compute formula fields on *merged* then copy changed values back into *update_data*."""
        await compute_formulas(dt, merged)
        for field in dt.fields:
            if (
                field.formula
                and field.fieldname in merged
                and field.fieldname not in PROTECTED_FIELDS
            ):
                update_data[field.fieldname] = merged[field.fieldname]

    async def _build_update_result(
        self,
        doctype_name: str,
        real_id: str,
        dt: Any,
        merged: dict[str, Any],
    ) -> dict[str, Any]:
        """Serialise, load child tables, and attach MultiLink fields for the response."""
        result = dict(merged)
        for k, v in result.items():
            if isinstance(v, datetime):
                result[k] = v.isoformat()
        await _load_child_tables(self.session, dt, result)
        ml_fields = _get_multi_link_fields(dt)
        if ml_fields:
            ml_data = await self._ml.get_all_for_doc(doctype_name, real_id)
            for mlf in ml_fields:
                result[mlf.fieldname] = ml_data.get(mlf.fieldname, [])
        return result

    async def _run_update_before_hooks(self, doc: Any) -> None:
        """Run validate/before_save hooks and normalize hook errors."""
        try:
            await doc.validate()
            await doc.before_save()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    async def _persist_update_doc(
        self,
        dt: Any,
        table: Any,
        doctype_name: str,
        real_id: str,
        data: dict[str, Any],
        row: dict[str, Any],
        update_data: dict[str, Any],
        user: User,
    ) -> None:
        """Apply update pipeline: formulas -> update row -> children -> aggregates -> MultiLink."""
        await self._propagate_formulas(dt, row, update_data)

        await self.session.execute(
            table.update().where(table.c.id == real_id).values(**update_data)
        )

        await _save_child_tables(self.session, dt, real_id, data, user, datetime.now(UTC))
        await self._apply_aggregations(dt, table, real_id, row)

        for mlf in _get_multi_link_fields(dt):
            if mlf.fieldname not in data:
                continue
            values = data[mlf.fieldname]
            if isinstance(values, list):
                await self._ml.set_values(
                    doctype_name,
                    real_id,
                    mlf.fieldname,
                    mlf.options or "",
                    values,
                )

        await self.session.flush()

    async def _run_update_after_hooks(self, doc: Any) -> None:
        """Run after_save hooks and normalize hook errors."""
        try:
            await doc.after_save()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    async def _run_delete_before_hooks(self, doc: Any) -> None:
        """Run before_delete hook and normalize hook errors."""
        try:
            await doc.before_delete()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    async def _run_delete_after_hooks(self, doc: Any) -> None:
        """Run after_delete hook and normalize hook errors."""
        try:
            await doc.after_delete()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    # ── Update ────────────────────────────────────────────────────────────

    async def update_document(
        self,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        user: User,
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            return await _virtual_update(doctype_name, user, doc_id, data)

        table = compile_doctype_to_table(dt)
        existing = await self.get_document(doctype_name, doc_id, user)

        errors = _validate_data(dt, data, partial=True, ignore_required=ignore_required)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors
            )

        update_data = self._build_update_payload(dt, table, data, user)
        real_id = existing["id"]
        merged = {**existing, **update_data}

        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, merged, user, self.session)
            await self._run_update_before_hooks(doc)
            await self._persist_update_doc(
                dt,
                table,
                doctype_name,
                real_id,
                data,
                merged,
                update_data,
                user,
            )
            logger.info("document.updated", doctype=doctype_name, id=real_id)

            result = await self._build_update_result(doctype_name, real_id, dt, merged)
            await record_update_changes(
                session=self.session,
                engine=self.engine,
                doctype_name=doctype_name,
                real_id=real_id,
                dt=dt,
                existing=existing,
                result=result,
                user=user,
            )

            doc.data = result
            await self._run_update_after_hooks(doc)

            await fire_update_services(
                session=self.session,
                doctype_name=doctype_name,
                dt=dt,
                result=result,
            )
            return result
        finally:
            self._reset_grunt_context(_tokens)

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: User,
    ) -> None:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            await _virtual_delete(doctype_name, user, doc_id)
            return

        table = compile_doctype_to_table(dt)

        existing = await self.get_document(doctype_name, doc_id, user)

        if dt.is_submittable and existing.get("docstatus") == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Скасуйте документ перед видаленням",
            )

        real_id = existing["id"]

        # Custom Controller Hooks
        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, existing, user, self.session)
            await self._run_delete_before_hooks(doc)
            await delete_row_and_links(
                session=self.session,
                ml=self._ml,
                table=table,
                doctype_name=doctype_name,
                real_id=real_id,
            )
            await fire_delete_services(
                session=self.session,
                doctype_name=doctype_name,
                real_id=real_id,
                existing=existing,
            )
            await self._run_delete_after_hooks(doc)

        finally:
            self._reset_grunt_context(_tokens)

    async def bulk_delete(
        self,
        doctype_name: str,
        ids: list[str],
        user: User,
        progress_cb: Any | None = None,
    ) -> tuple[int, list[str]]:
        """Delete multiple documents efficiently in a single transaction.

        Runs per-document hooks (before/after_delete) but batches all DB
        writes (DELETE, multi-link cleanup, search index) into one flush.

        ``progress_cb`` is an optional async callable
        ``(done: int, total: int, errors: int) -> None`` called after each
        before_delete hook phase and once after the batch commit.

        Returns ``(deleted_count, error_messages)``.
        """
        if not ids:
            return 0, []

        dt = await doctype_registry.get(doctype_name)

        if dt.is_virtual:
            return await bulk_delete_virtual(
                doctype_name=doctype_name,
                ids=ids,
                user=user,
            )

        table = compile_doctype_to_table(dt)
        to_delete, errors = await collect_bulk_delete_candidates(
            session=self.session,
            dt=dt,
            table=table,
            ids=ids,
        )

        if not to_delete:
            return 0, errors

        total = len(ids)

        async def _report(done: int) -> None:
            if progress_cb is not None:
                await progress_cb(done, total, len(errors))

        _tokens = self._set_grunt_context(user)
        try:
            controllers = await run_bulk_before_delete_hooks(
                doctype_name=doctype_name,
                docs=to_delete,
                user=user,
                session=self.session,
                errors=errors,
                report=_report,
            )
        finally:
            self._reset_grunt_context(_tokens)

        if not controllers:
            return 0, errors

        final_ids = [str(d["id"]) for d, _ in controllers]

        _tokens = self._set_grunt_context(user)
        try:
            await run_bulk_delete_writes(
                session=self.session,
                ml=self._ml,
                table=table,
                doctype_name=doctype_name,
                final_ids=final_ids,
            )
            await run_bulk_after_delete_hooks(
                session=self.session,
                doctype_name=doctype_name,
                controllers=controllers,
                errors=errors,
            )
        finally:
            self._reset_grunt_context(_tokens)

        deleted = len(final_ids)
        await _report(total)
        return deleted, errors

    async def rename_document(
        self,
        doctype_name: str,
        old_id: str,
        new_id: str,
        user: User,
    ) -> dict[str, Any]:
        """Update the primary ID of a document and cascade changes to all references."""
        if old_id == new_id:
            return await self.get_document(doctype_name, old_id, user)

        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rename virtual documents",
            )

        table = compile_doctype_to_table(dt)

        # 0. Check if new_id already exists
        exists_q = select(table.c.id).where(table.c.id == new_id)
        exists_res = await self.session.execute(exists_q)
        if exists_res.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document with ID '{new_id}' already exists",
            )

        # Fetch document before rename for hooks
        doc_data = await self.get_document(doctype_name, old_id, user)

        # 1. Update main table
        # We update both 'id' and 'name' to keep them in sync for autonamed docs
        await self.session.execute(
            table.update().where(table.c.id == old_id).values(id=new_id, name=new_id)
        )

        # 2. Update references across all DocTypes
        all_dts = await doctype_registry.list_all()
        for other_dt in all_dts:
            # A. Update child tables (Tables)
            is_child = any(
                f.fieldtype == "Table" and f.options == other_dt.name for f in dt.fields
            )
            if is_child:
                child_table = compile_doctype_to_table(other_dt)
                await self.session.execute(
                    child_table.update()
                    .where(child_table.c.parent_id == old_id)
                    .values(parent_id=new_id)
                )

            # B. Update Link fields referencing our doctype
            for f in other_dt.fields:
                if f.fieldtype == "Link" and f.options == doctype_name:
                    ref_table = compile_doctype_to_table(other_dt)
                    await self.session.execute(
                        ref_table.update()
                        .where(ref_table.c[f.fieldname] == old_id)
                        .values(**{f.fieldname: new_id})
                    )

        # 3. Update MultiLink references
        from grunt.core.metadata.compiler import MULTI_LINK_TABLE  # noqa: PLC0415

        await self.session.execute(
            update(MULTI_LINK_TABLE)
            .where(
                MULTI_LINK_TABLE.c.parent_id == old_id,
                MULTI_LINK_TABLE.c.parent_doctype == doctype_name,
            )
            .values(parent_id=new_id)
        )
        await self.session.execute(
            update(MULTI_LINK_TABLE)
            .where(
                MULTI_LINK_TABLE.c.link_name == old_id,
                MULTI_LINK_TABLE.c.link_doctype == doctype_name,
            )
            .values(link_name=new_id)
        )

        # 4. Update system DocTypes
        system_refs = [
            ("ActivityLog", "doc_id"),
            ("DocVersion", "doc_id"),
            ("File", "doc_id"),
            ("File", "parent_id"),
            ("Comment", "parent_id"),
            ("EmailQueue", "doc_id"),
        ]
        for sys_dt_name, sys_fieldname in system_refs:
            try:
                sys_dt = await doctype_registry.get(sys_dt_name)
                sys_table = compile_doctype_to_table(sys_dt)
                if sys_fieldname in sys_table.c:
                    await self.session.execute(
                        sys_table.update()
                        .where(sys_table.c[sys_fieldname] == old_id)
                        .values(**{sys_fieldname: new_id})
                    )
            except Exception:  # noqa: BLE001
                continue

        await self.session.flush()

        # 5. Update Search Index (delete old, index new)
        from grunt.core.search.service import search_index_service  # noqa: PLC0415

        await search_index_service.remove_document(self.session, doctype_name, old_id)
        # Re-fetch with new ID for indexing
        new_doc = await self.get_document(doctype_name, new_id, user)
        await search_index_service.index_document(self.session, doctype_name, dt, new_doc)

        logger.info("document.renamed", doctype=doctype_name, old=old_id, new=new_id)
        return new_doc
