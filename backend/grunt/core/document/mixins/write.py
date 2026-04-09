"""Mixin classes for DocumentService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.document.multi_link import MultiLinkService

from grunt.app import GruntError
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
from grunt.core.hooks import fire
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

PROTECTED_FIELDS = frozenset({"id", "owner", "created_at", "docstatus"})


class DocumentWriteMixin:
    session: AsyncSession
    engine: AsyncEngine
    _ml: MultiLinkService

    def _set_grunt_context(self, user: GruntUser) -> tuple: ...

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None: ...

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

        now = datetime.now(UTC)
        doc_id = str(uuid.uuid4())

        # Generate document name
        from grunt.core.naming import naming_service  # noqa: PLC0415

        generated_name = await naming_service.generate(dt.autoname or "", data, self.session)

        row: dict[str, Any] = {}
        standard = {
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
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                ) from e

            await fire(
                "before_save", doctype=doctype_name, doc=row, user=user, session=self.session
            )

            await self.session.execute(table.insert().values(**row))
            await self.session.flush()

            # Save child table fields
            await _save_child_tables(self.session, dt, doc_id, data, user, now)

            # Save MultiLink fields
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

            logger.info("document.created", doctype=doctype_name, id=doc_id)

            try:
                await doc.after_insert()
                await doc.after_save()
            except GruntError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                ) from e

            await fire(
                "after_insert", doctype=doctype_name, doc=row, user=user, session=self.session
            )
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

        if "modified_at" in table.c:
            update_data["modified_at"] = datetime.now(UTC)
        if "modified_by" in table.c:
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
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                ) from e

            await fire(
                "before_save", doctype=doctype_name, doc=merged, user=user, session=self.session
            )

            await self.session.execute(
                table.update().where(table.c.id == real_id).values(**update_data)
            )

            # Update child table fields
            await _save_child_tables(self.session, dt, real_id, data, user, datetime.now(UTC))

            # Update MultiLink fields
            for mlf in _get_multi_link_fields(dt):
                if mlf.fieldname in data:
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
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                ) from e

            await fire(
                "after_update", doctype=doctype_name, doc=result, user=user, session=self.session
            )
            await fire(
                "after_save", doctype=doctype_name, doc=result, user=user, session=self.session
            )

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
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                ) from e

            await fire(
                "before_delete", doctype=doctype_name, doc=existing, user=user, session=self.session
            )

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
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                ) from e

            await fire(
                "after_delete",
                doctype=doctype_name,
                doc_id=real_id,
                user=user,
                session=self.session,
            )
        finally:
            self._reset_grunt_context(_tokens)
