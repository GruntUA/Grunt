"""Mixin classes for DocumentService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from itertools import islice
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select

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

        doc_id = str(data.get("id") or uuid.uuid4())
        generated_name = await naming_service.generate(dt.autoname or "", data, self.session)

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
        compute_formulas(dt, row)
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
    def _propagate_formulas(
        dt: Any, merged: dict[str, Any], update_data: dict[str, Any]
    ) -> None:
        """Compute formula fields on *merged* then copy changed values back into *update_data*."""
        compute_formulas(dt, merged)
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

    async def _record_changes(
        self,
        doctype_name: str,
        real_id: str,
        dt: Any,
        existing: dict[str, Any],
        result: dict[str, Any],
        user: User,
    ) -> None:
        """Create a version record and write an ActivityLog diff (both best-effort)."""
        from grunt.core.document.versioning import version_service  # noqa: PLC0415

        diff_changes = version_service._compute_diff(existing, result)

        if dt.track_changes and diff_changes:
            try:
                await version_service.create_version(
                    session=self.session,
                    doctype=doctype_name,
                    doc_id=real_id,
                    old_doc=existing,
                    new_doc=result,
                    user=user.email,
                )
            except Exception:
                logger.exception("version.create_error", doctype=doctype_name, doc_id=real_id)

        if diff_changes:
            try:
                from grunt.app import grunt as _g  # noqa: PLC0415

                async with _g.context(session=self.session, engine=self.engine, user=user):
                    await _g.new_doc(
                        "ActivityLog",
                        {
                            "doctype": doctype_name,
                            "doc_id": real_id,
                            "action": "Update",
                            "user": user.email,
                            "details": {"changes": diff_changes},
                        },
                    )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "activity_log.update_failed", doctype=doctype_name, doc_id=real_id
                )

    async def _fire_update_services(
        self, doctype_name: str, dt: Any, result: dict[str, Any]
    ) -> None:
        """Update the search index and fire outgoing webhooks after a successful update."""
        from grunt.core.search.service import search_index_service  # noqa: PLC0415
        from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

        await search_index_service.index_document(self.session, doctype_name, dt, result)
        await webhook_service.fire(self.session, "after_update", doctype_name, result)

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
        self._propagate_formulas(dt, row, update_data)

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

    async def _delete_row_and_links(
        self,
        table: Any,
        doctype_name: str,
        real_id: str,
    ) -> None:
        """Delete main row and MultiLink relations, then flush pending writes."""
        await self.session.execute(table.delete().where(table.c.id == real_id))
        await self._ml.delete_all_for_doc(doctype_name, real_id)
        await self.session.flush()

    async def _fire_delete_services(
        self,
        doctype_name: str,
        real_id: str,
        existing: dict[str, Any],
    ) -> None:
        """Update external services after delete: search index and outgoing webhooks."""
        from grunt.core.search.service import search_index_service  # noqa: PLC0415
        from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

        await search_index_service.remove_document(self.session, doctype_name, real_id)
        await webhook_service.fire(self.session, "after_delete", doctype_name, existing)

    async def _run_delete_after_hooks(self, doc: Any) -> None:
        """Run after_delete hook and normalize hook errors."""
        try:
            await doc.after_delete()
        except GruntError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            ) from e

    async def _bulk_delete_virtual(
        self,
        doctype_name: str,
        ids: list[str],
        user: User,
    ) -> tuple[int, list[str]]:
        """Delete virtual documents one-by-one and aggregate errors."""
        deleted = 0
        errors: list[str] = []
        for doc_id in ids:
            try:
                await _virtual_delete(doctype_name, user, doc_id)
                deleted += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"{doc_id}: {e}")
        return deleted, errors

    async def _collect_bulk_delete_candidates(
        self,
        dt: Any,
        table: Any,
        ids: list[str],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Fetch and validate candidate docs for bulk delete."""
        from sqlalchemy import select as sa_select  # noqa: PLC0415

        existing_rows: dict[str, dict[str, Any]] = {}
        result = await self.session.execute(sa_select(table).where(table.c.id.in_(ids)))
        for row in result.fetchall():
            existing_rows[str(row._mapping["id"])] = dict(row._mapping)

        errors: list[str] = []
        to_delete: list[dict[str, Any]] = []

        for doc_id in ids:
            doc = existing_rows.get(doc_id)
            if doc is None:
                errors.append(f"{doc_id}: not found")
                continue
            if dt.is_submittable and doc.get("docstatus") == 1:
                errors.append(f"{doc_id}: submitted — cancel before delete")
                continue
            to_delete.append(doc)

        return to_delete, errors

    async def _run_bulk_before_delete_hooks(
        self,
        doctype_name: str,
        docs: list[dict[str, Any]],
        user: User,
        errors: list[str],
        report: Any | None = None,
    ) -> list[tuple[dict[str, Any], Any]]:
        """Run per-document before_delete hooks and keep only successful controllers."""
        controllers: list[tuple[dict[str, Any], Any]] = []
        for i, doc in enumerate(docs):
            controller_cls = document_registry.get(doctype_name)
            ctrl = controller_cls(doctype_name, doc, user, self.session)
            try:
                await ctrl.before_delete()
            except GruntError as e:
                errors.append(f"{doc['id']}: {e}")
                continue
            controllers.append((doc, ctrl))
            if report is not None:
                await report(i + 1)
        return controllers

    async def _run_bulk_delete_writes(
        self,
        table: Any,
        doctype_name: str,
        final_ids: list[str],
    ) -> None:
        """Execute batched DELETE + MultiLink cleanup + search index cleanup."""
        from grunt.core.search.service import search_index_service  # noqa: PLC0415

        await self.session.execute(table.delete().where(table.c.id.in_(final_ids)))
        await self._ml.delete_all_for_docs(doctype_name, final_ids)
        await self.session.flush()
        await search_index_service.remove_documents(self.session, doctype_name, final_ids)

    async def _run_bulk_after_delete_hooks(
        self,
        doctype_name: str,
        controllers: list[tuple[dict[str, Any], Any]],
        errors: list[str],
    ) -> None:
        """Run per-document after_delete hooks and fire outgoing webhooks."""
        from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

        for doc, ctrl in controllers:
            real_id = str(doc["id"])
            try:
                await ctrl.after_delete()
            except GruntError as e:
                errors.append(f"{real_id}: {e}")
            await webhook_service.fire(self.session, "after_delete", doctype_name, doc)

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

        errors = _validate_data(dt, data, ignore_required=ignore_required)
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
            await self._record_changes(doctype_name, real_id, dt, existing, result, user)

            doc.data = result
            await self._run_update_after_hooks(doc)

            await self._fire_update_services(doctype_name, dt, result)
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
            await self._delete_row_and_links(table, doctype_name, real_id)
            await self._fire_delete_services(doctype_name, real_id, existing)
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
            return await self._bulk_delete_virtual(doctype_name, ids, user)

        table = compile_doctype_to_table(dt)
        to_delete, errors = await self._collect_bulk_delete_candidates(dt, table, ids)

        if not to_delete:
            return 0, errors

        total = len(ids)

        async def _report(done: int) -> None:
            if progress_cb is not None:
                await progress_cb(done, total, len(errors))

        _tokens = self._set_grunt_context(user)
        try:
            controllers = await self._run_bulk_before_delete_hooks(
                doctype_name,
                to_delete,
                user,
                errors,
                _report,
            )
        finally:
            self._reset_grunt_context(_tokens)

        if not controllers:
            return 0, errors

        final_ids = [str(d["id"]) for d, _ in controllers]

        _tokens = self._set_grunt_context(user)
        try:
            await self._run_bulk_delete_writes(table, doctype_name, final_ids)
            await self._run_bulk_after_delete_hooks(doctype_name, controllers, errors)
        finally:
            self._reset_grunt_context(_tokens)

        deleted = len(final_ids)
        await _report(total)
        return deleted, errors
