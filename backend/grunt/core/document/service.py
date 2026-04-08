"""DocumentService — dynamic CRUD for any DocType.

Knows nothing about specific schemas ahead of time; everything comes from the
DocType registry at runtime.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.models import GruntUser
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry
from grunt.core.hooks import fire
from grunt.core.document.registry import document_registry
from grunt.core.document.multi_link import MultiLinkService
from grunt.app import grunt as _grunt, GruntError

# Sub-module imports
from grunt.core.document.query import _apply_filters, _apply_search
from grunt.core.document.relations import _load_child_tables, _save_child_tables, _get_multi_link_fields
from grunt.core.document.validation import _coerce_value, _validate_data
from grunt.core.document.virtual import (
    _virtual_list,
    _virtual_get,
    _virtual_create,
    _virtual_update,
    _virtual_delete,
)

logger = structlog.get_logger()

# Fields that users may never set or overwrite
PROTECTED_FIELDS = frozenset({"id", "owner", "created_at", "docstatus"})


class DocumentService:
    """Dynamic CRUD for any registered DocType."""

    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self.session = session
        self.engine = engine
        self._ml = MultiLinkService(session)

    def _set_grunt_context(self, user: GruntUser) -> tuple:
        """Activate the grunt ContextVar context for the current lifecycle scope."""
        return _grunt.set_context(session=self.session, engine=self.engine, user=user)

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None:
        _grunt.reset_context(tokens)

    # ── List ──────────────────────────────────────────────────────────────

    async def list_documents(
        self,
        doctype_name: str,
        user: GruntUser,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "modified_at",
        sort_order: str = "desc",
        filters: dict[str, str] | None = None,
        search: str | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)

        # Virtual DocType — delegate to sub-module
        if dt.is_virtual:
            return await _virtual_list(doctype_name, user, page, per_page, sort_by, sort_order, filters, search)

        table = compile_doctype_to_table(dt)

        # Singleton — return at most 1 row, ignore pagination
        if dt.is_singleton:
            result = await self.session.execute(select(table).limit(1))
            row = result.first()
            data_list = [dict(row._mapping)] if row else []
            for r in data_list:
                for k, v in r.items():
                    if isinstance(v, datetime):
                        r[k] = v.isoformat()
            return {
                "data": data_list,
                "meta": {"total": len(data_list), "page": 1, "per_page": 1, "pages": 1},
            }

        # Select columns
        if fields:
            required = {"id", "name", "modified_at", "docstatus"}
            requested = required | set(fields)
            cols = [table.c[c] for c in requested if c in table.c]
        else:
            cols = [table]

        query = select(*cols)

        # Filters
        if filters:
            query = _apply_filters(query, table, filters)

        # Search
        if search:
            query = _apply_search(query, table, dt, search)

        # Count
        count_q = select(func.count()).select_from(table)
        if filters:
            count_q = _apply_filters(count_q, table, filters)
        if search:
            count_q = _apply_search(count_q, table, dt, search)
        count_result = await self.session.execute(count_q)
        total = count_result.scalar() or 0

        # Sort
        sort_col = table.c.get(sort_by, table.c.modified_at)
        TEXT_TYPES = {"TEXT", "VARCHAR", "CHAR", "CLOB", "STRING", "NVARCHAR", "NCHAR"}
        col_type = str(sort_col.type).upper()
        is_text = any(t in col_type for t in TEXT_TYPES)
        if is_text:
            from sqlalchemy import func as sa_func  # noqa: PLC0415
            sort_expr = sa_func.uk_sort_key(sort_col)
        else:
            sort_expr = sort_col
        if sort_order == "asc":
            query = query.order_by(sort_expr.asc())
        else:
            query = query.order_by(sort_expr.desc())

        # Pagination
        offset = (page - 1) * per_page
        query = query.limit(per_page).offset(offset)

        result = await self.session.execute(query)
        rows = [dict(row._mapping) for row in result]

        # Serialise datetimes
        for row in rows:
            for k, v in row.items():
                if isinstance(v, datetime):
                    row[k] = v.isoformat()

        # Apply field-level permissions
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        hidden = permission_checker.hidden_fields(user, dt)
        if hidden:
            for row in rows:
                for field in hidden:
                    row.pop(field, None)

        return {
            "data": rows,
            "meta": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
            },
        }

    # ── Create ────────────────────────────────────────────────────────────

    async def create_document(
        self,
        doctype_name: str,
        data: dict[str, Any],
        user: GruntUser,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            return await _virtual_create(doctype_name, user, data)

        table = compile_doctype_to_table(dt)

        # Singleton — allow only one document
        if dt.is_singleton:
            existing = await self.session.execute(select(func.count()).select_from(table))
            if (existing.scalar() or 0) > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"'{doctype_name}' is a singleton.",
                )

        if doctype_registry.is_system(doctype_name) and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' is managed by the system.",
            )

        # Validate
        errors = _validate_data(dt, data)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=errors,
            )

        now = datetime.now(timezone.utc)
        doc_id = str(uuid.uuid4())

        # Generate document name
        from grunt.core.naming import naming_service  # noqa: PLC0415
        generated_name = await naming_service.generate(dt.autoname or "", data, self.session)

        row = {
            "id": doc_id,
            "name": generated_name or doc_id[:8],
            "owner": user.email,
            "created_at": now,
            "modified_at": now,
            "modified_by": user.email,
            "docstatus": 0,
        }

        # Copy user-supplied fields
        from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname in data:
                row[field.fieldname] = _coerce_value(data[field.fieldname], field.fieldtype)
            elif field.default is not None:
                row[field.fieldname] = _coerce_value(field.default, field.fieldtype)
            elif field.fieldtype == "Check":
                row[field.fieldname] = False

        # Copy workflow state field
        if dt.workflow:
            sf = dt.workflow.state_field
            if sf in data:
                row[sf] = data[sf]
            elif sf not in row:
                initial = next((s for s in dt.workflow.states if s.is_initial), None)
                if initial:
                    row[sf] = initial.name

        # Custom Controller Hooks
        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, row, user, self.session)
            try:
                await doc.validate()
                await doc.before_insert()
                await doc.before_save()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("before_save", doctype=doctype_name, doc=row, user=user, session=self.session)

            await self.session.execute(table.insert().values(**row))
            await self.session.flush()

            # Save child table fields
            await _save_child_tables(self.session, dt, doc_id, data, user, now)

            # Save MultiLink fields
            for mlf in _get_multi_link_fields(dt):
                values = data.get(mlf.fieldname)
                if isinstance(values, list):
                    await self._ml.set_values(
                        doctype_name, doc_id, mlf.fieldname,
                        mlf.options or "", values,
                    )

            logger.info("document.created", doctype=doctype_name, id=doc_id)

            try:
                await doc.after_insert()
                await doc.after_save()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("after_insert", doctype=doctype_name, doc=row, user=user, session=self.session)
            await fire("after_save", doctype=doctype_name, doc=row, user=user, session=self.session)

            # Update search index
            from grunt.core.search.service import search_index_service  # noqa: PLC0415
            await search_index_service.index_document(self.session, doctype_name, dt, row)

            # Fire outgoing webhooks
            from grunt.core.webhook.service import webhook_service  # noqa: PLC0415
            await webhook_service.fire(self.session, "after_insert", doctype_name, row)

        finally:
            self._reset_grunt_context(_tokens)

        # Serialise datetimes
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()

        # Attach MultiLink values
        for mlf in _get_multi_link_fields(dt):
            row[mlf.fieldname] = await self._ml.get_values(doctype_name, doc_id, mlf.fieldname)

        return row

    # ── Get ────────────────────────────────────────────────────────────

    async def get_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: GruntUser,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            return await _virtual_get(doctype_name, user, doc_id)

        table = compile_doctype_to_table(dt)

        query = select(table).where(
            (table.c.id == doc_id) | (table.c.name == doc_id)
        )
        result = await self.session.execute(query)
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found.",
            )

        doc = dict(row._mapping)
        for k, v in doc.items():
            if isinstance(v, datetime):
                doc[k] = v.isoformat()

        # Attach child table values
        await _load_child_tables(self.session, dt, doc)

        # Attach MultiLink values
        ml_fields = _get_multi_link_fields(dt)
        if ml_fields:
            ml_data = await self._ml.get_all_for_doc(doctype_name, doc["id"])
            for mlf in ml_fields:
                doc[mlf.fieldname] = ml_data.get(mlf.fieldname, [])

        # Apply field-level permissions
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415
        hidden = permission_checker.hidden_fields(user, dt)
        for field in hidden:
            doc.pop(field, None)

        return doc

    # ── Update ────────────────────────────────────────────────────────────

    async def update_document(
        self,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        user: GruntUser,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            return await _virtual_update(doctype_name, user, doc_id, data)

        if doctype_registry.is_system(doctype_name) and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' is managed by the system.",
            )
        table = compile_doctype_to_table(dt)

        # Ensure document exists
        existing = await self.get_document(doctype_name, doc_id, user)

        # Validate partial
        errors = _validate_data(dt, data, partial=True)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=errors,
            )

        # Strip protected fields
        update_data: dict[str, Any] = {}
        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                update_data[field.fieldname] = _coerce_value(data[field.fieldname], field.fieldtype)

        update_data["modified_at"] = datetime.now(timezone.utc)
        update_data["modified_by"] = user.email

        real_id = existing["id"]
        merged = {**existing, **update_data}

        # Custom Controller Hooks
        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            doc = controller_cls(doctype_name, merged, user, self.session)
            try:
                await doc.validate()
                await doc.before_save()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("before_save", doctype=doctype_name, doc=merged, user=user, session=self.session)

            await self.session.execute(
                table.update().where(table.c.id == real_id).values(**update_data)
            )

            # Update child table fields
            await _save_child_tables(self.session, dt, real_id, data, user, datetime.now(timezone.utc))

            # Update MultiLink fields
            for mlf in _get_multi_link_fields(dt):
                if mlf.fieldname in data:
                    values = data[mlf.fieldname]
                    if isinstance(values, list):
                        await self._ml.set_values(
                            doctype_name, real_id, mlf.fieldname,
                            mlf.options or "", values,
                        )

            await self.session.flush()

            logger.info("document.updated", doctype=doctype_name, id=real_id)

            # Build result
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
            from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415
            for field in permission_checker.hidden_fields(user, dt):
                result.pop(field, None)

            # Create version record
            if dt.track_changes:
                from grunt.core.document.versioning import version_service  # noqa: PLC0415
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

            doc.data = result
            try:
                await doc.after_save()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("after_update", doctype=doctype_name, doc=result, user=user, session=self.session)
            await fire("after_save", doctype=doctype_name, doc=result, user=user, session=self.session)

            # Update search index
            from grunt.core.search.service import search_index_service  # noqa: PLC0415
            await search_index_service.index_document(self.session, doctype_name, dt, result)

            # Fire webhooks
            from grunt.core.webhook.service import webhook_service  # noqa: PLC0415
            await webhook_service.fire(self.session, "after_update", doctype_name, result)

            return result
        finally:
            self._reset_grunt_context(_tokens)

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: GruntUser,
    ) -> None:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            await _virtual_delete(doctype_name, user, doc_id)
            return

        if doctype_registry.is_system(doctype_name) and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' is managed by the system.",
            )
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
            try:
                await doc.before_delete()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("before_delete", doctype=doctype_name, doc=existing, user=user, session=self.session)

            await self.session.execute(table.delete().where(table.c.id == real_id))
            await self._ml.delete_all_for_doc(doctype_name, real_id)
            await self.session.flush()

            # Remove from search index
            from grunt.core.search.service import search_index_service  # noqa: PLC0415
            await search_index_service.remove_document(self.session, doctype_name, real_id)

            # Fire webhooks
            from grunt.core.webhook.service import webhook_service  # noqa: PLC0415
            await webhook_service.fire(self.session, "after_delete", doctype_name, existing)

            try:
                await doc.after_delete()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("after_delete", doctype=doctype_name, doc_id=real_id, user=user, session=self.session)
        finally:
            self._reset_grunt_context(_tokens)
