"""Mixin classes for DocumentService."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.document.multi_link import MultiLinkService

from grunt.app import GruntError
from grunt.document.aggregate import compute_aggregations
from grunt.document.formula import compute_formulas
from grunt.document.registry import document_registry
from grunt.document.relations import (
    _get_multi_link_fields,
    _load_child_tables,
    _save_child_tables,
)
from grunt.document.update_side_effects import (
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
from grunt.document.validation import _validate_data
from grunt.document.virtual import (
    is_virtual_routed,
    virtual_create,
    virtual_delete,
    virtual_update,
)
from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry

logger = structlog.get_logger()

PROTECTED_FIELDS = frozenset({"name", "owner", "created_at", "docstatus"})


def _friendly_integrity_error(exc: IntegrityError, dt: Any) -> HTTPException:
    """Convert a DB IntegrityError into a user-friendly 409 HTTPException."""
    import re

    raw = str(exc.orig or exc)
    # SQLite: "UNIQUE constraint failed: table.column"
    # PostgreSQL: 'duplicate key value violates unique constraint "uq_..."'
    col_name: str | None = None
    m = re.search(r"UNIQUE constraint failed:\s*\S+\.(\w+)", raw, re.IGNORECASE)
    if m:
        col_name = m.group(1)
    else:
        # PostgreSQL via constraint name: uq_{table}_{fieldname}
        m2 = re.search(r'"uq_[^"]+?_(\w+)"', raw)
        if m2:
            col_name = m2.group(1)

    if col_name and dt is not None:
        label = next(
            (f.label or f.fieldname for f in dt.fields if f.fieldname == col_name),
            col_name,
        )
        message = f"Значення поля «{label}» вже існує в системі. Введіть унікальне значення."
    else:
        message = "Запис з таким значенням вже існує. Введіть унікальне значення."

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


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
        from grunt.naming import naming_service

        controller_cls = document_registry.get(dt.name)
        custom_autoname = getattr(controller_cls, "autoname", None)
        if custom_autoname is not None and callable(custom_autoname):
            doc_name = await custom_autoname(data, self.session)
        else:
            doc_name = await naming_service.generate(dt.autoname or "", data, self.session)

        row: dict[str, Any] = {}
        standard: dict[str, Any] = {
            "name": doc_name,
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
            if not field.is_physical:
                continue
            if field.fieldname in data:
                row[field.fieldname] = field.coerce(data[field.fieldname])
            elif field.default is not None:
                row[field.fieldname] = field.coerce(field.default)
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

        return doc_name, row

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
        table_cols = {c.name for c in table.c}
        db_row = {k: v for k, v in row.items() if k in table_cols}
        await self.session.execute(table.insert().values(**db_row))
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
            table.update().where(table.c.name == doc_id).values(**agg_values)
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

    async def _fire_create_services(self, doctype_name: str, dt: Any, row: dict[str, Any]) -> None:
        """Update the search index and fire outgoing webhooks after a successful insert."""
        from grunt.search.service import search_index_service
        from grunt.webhook.service import webhook_service

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
        fresh = await doctype_registry._lazy_load(doctype_name)
        dt = fresh if fresh is not None else await doctype_registry.get(doctype_name)
        if is_virtual_routed(dt, doctype_name):
            return await virtual_create(doctype_name, user, data)

        table = compile_doctype_to_table(dt)
        await self._check_singleton(dt, table)

        errors = _validate_data(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        now = datetime.now(UTC)
        doc_id, row = await self._build_initial_row(dt, table, data, user, now)

        _tokens = self._set_grunt_context(user)
        try:
            await self._persist_new_doc(dt, table, doctype_name, doc_id, data, row, user, now)
            await self._fire_create_services(doctype_name, dt, row)
        except IntegrityError as exc:
            raise _friendly_integrity_error(exc, dt) from exc
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
            if not field.is_physical:
                continue
            if field.fieldname not in table_columns:
                continue
            if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                update_data[field.fieldname] = field.coerce(data[field.fieldname])
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
            table.update().where(table.c.name == real_id).values(**update_data)
        )

        await _save_child_tables(self.session, dt, real_id, row, user, datetime.now(UTC))
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
        fresh = await doctype_registry._lazy_load(doctype_name)
        dt = fresh if fresh is not None else await doctype_registry.get(doctype_name)
        if is_virtual_routed(dt, doctype_name):
            return await virtual_update(doctype_name, user, doc_id, data)

        table = compile_doctype_to_table(dt)
        existing = await self.get_document(doctype_name, doc_id, user)

        errors = _validate_data(dt, data, partial=True, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        update_data = self._build_update_payload(dt, table, data, user)
        real_id = existing["name"]
        merged = {**existing, **update_data}
        # Inject submitted child-table rows into merged so lifecycle hooks see the
        # incoming data (not the old DB rows) and their mutations are persisted.
        for _f in dt.fields:
            if _f.fieldtype == "Table" and _f.fieldname in data:
                merged[_f.fieldname] = data[_f.fieldname]

        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, merged, user, self.session)
            await self._run_update_before_hooks(doc)

            # Sync hook mutations: any physical field that validate()/before_save()
            # changed in `merged` must be written to the DB even if the frontend
            # did not submit it (e.g. read-only computed fields).
            _table_cols = {c.name for c in table.columns}
            for _f in dt.fields:
                if (
                    not _f.is_physical
                    or _f.fieldname in PROTECTED_FIELDS
                    or _f.fieldname not in _table_cols
                ):
                    continue
                _merged_val = merged.get(_f.fieldname)
                if _merged_val != existing.get(_f.fieldname):
                    update_data[_f.fieldname] = _merged_val

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
        except IntegrityError as exc:
            raise _friendly_integrity_error(exc, dt) from exc
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
        if is_virtual_routed(dt, doctype_name):
            await virtual_delete(doctype_name, user, doc_id)
            return

        table = compile_doctype_to_table(dt)

        existing = await self.get_document(doctype_name, doc_id, user)

        if dt.is_submittable and existing.get("docstatus") == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Скасуйте документ перед видаленням",
            )

        real_id = existing["name"]

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

        if is_virtual_routed(dt, doctype_name):
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

        final_ids = [str(d["name"]) for d, _ in controllers]

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
        if is_virtual_routed(dt, doctype_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rename virtual documents",
            )

        table = compile_doctype_to_table(dt)

        # 0. Check if new_id already exists
        exists_q = select(table.c.name).where(table.c.name == new_id)
        exists_res = await self.session.execute(exists_q)
        if exists_res.first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document with name '{new_id}' already exists",
            )

        # 1. Update main table
        await self.session.execute(table.update().where(table.c.name == old_id).values(name=new_id))

        # 2. Update references across all DocTypes
        all_dts = await doctype_registry.list_all()
        for other_dt in all_dts:
            # A. Update child tables (Tables)
            is_child = any(f.fieldtype == "Table" and f.options == other_dt.name for f in dt.fields)
            if is_child:
                child_table = compile_doctype_to_table(other_dt)
                await self.session.execute(
                    child_table.update()
                    .where(child_table.c.parent_name == old_id)
                    .values(parent_name=new_id)
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
        from grunt.metadata.compiler import MULTI_LINK_TABLE

        await self.session.execute(
            update(MULTI_LINK_TABLE)
            .where(
                MULTI_LINK_TABLE.c.parent_name == old_id,
                MULTI_LINK_TABLE.c.parent_doctype == doctype_name,
            )
            .values(parent_name=new_id)
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
            ("File", "attached_to_id"),
            ("Comment", "reference_id"),
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
            except Exception:
                continue

        await self.session.flush()

        # 5. Update Search Index (delete old, index new)
        from grunt.search.service import search_index_service

        await search_index_service.remove_document(self.session, doctype_name, old_id)
        # Re-fetch with new ID for indexing
        new_doc = await self.get_document(doctype_name, new_id, user)
        await search_index_service.index_document(self.session, doctype_name, dt, new_doc)

        logger.info("document.renamed", doctype=doctype_name, old=old_id, new=new_id)
        return new_doc
