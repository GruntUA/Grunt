"""DocumentService — dynamic CRUD for any DocType.

Knows nothing about specific schemas ahead of time; everything comes from the
DocType registry at runtime.
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, time, timezone
from typing import Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.models import GruntUser
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
from grunt.core.metadata.registry import doctype_registry
from grunt.core.hooks import fire
from grunt.core.document.registry import document_registry
from grunt.core.document.multi_link import MultiLinkService
from grunt.app import grunt as _grunt, GruntError

logger = structlog.get_logger()

# Fields that users may never set or overwrite
PROTECTED_FIELDS = frozenset({"id", "owner", "created_at", "docstatus"})


def _get_multi_link_fields(dt: DocType) -> list:
    """Return MultiLink fields from a DocType."""
    return [f for f in dt.fields if f.fieldtype == "MultiLink"]


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

        # Virtual DocType — delegate to controller
        if dt.is_virtual:
            return await self._virtual_list(dt, doctype_name, user, page, per_page, sort_by, sort_order, filters, search)

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
            required = {"id", "name"}
            requested = required | set(fields)
            cols = [table.c[c] for c in requested if c in table.c]
        else:
            cols = [table]

        query = select(*cols)

        # Filters
        if filters:
            query = self._apply_filters(query, table, filters)

        # Search
        if search:
            query = self._apply_search(query, table, dt, search)

        # Count
        count_q = select(func.count()).select_from(query.subquery())
        count_result = await self.session.execute(count_q)
        total = count_result.scalar() or 0

        # Sort
        sort_col = table.c.get(sort_by, table.c.modified_at)
        if sort_order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

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
            return await self._virtual_create(dt, doctype_name, user, data)

        # Singleton — allow only one document
        if dt.is_singleton:
            table_check = compile_doctype_to_table(dt)
            existing = await self.session.execute(select(func.count()).select_from(table_check))
            if (existing.scalar() or 0) > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"'{doctype_name}' є singleton — документ вже існує. Використовуйте PUT для оновлення.",
                )

        if doctype_registry.is_system(doctype_name) and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' керується системою. Використовуйте відповідний API.",
            )
        dt = await doctype_registry.get(doctype_name)
        table = compile_doctype_to_table(dt)

        # Validate
        errors = self._validate_data(dt, data)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=errors,
            )

        now = datetime.now(timezone.utc)
        doc_id = str(uuid.uuid4())

        # Generate document name via NamingService
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

        # Copy user-supplied fields (only those that exist as columns)
        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname in data:
                row[field.fieldname] = self._coerce_value(data[field.fieldname], field.fieldtype)
            elif field.default is not None:
                row[field.fieldname] = self._coerce_value(field.default, field.fieldtype)
            elif field.fieldtype == "Check":
                row[field.fieldname] = False  # Check fields default to False, never NULL

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
        finally:
            self._reset_grunt_context(_tokens)

        # Serialise datetimes for response
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()

        # Attach MultiLink values to response
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
            return await self._virtual_get(dt, doctype_name, user, doc_id)

        table = compile_doctype_to_table(dt)

        query = select(table).where(
            (table.c.id == doc_id) | (table.c.name == doc_id)
        )
        result = await self.session.execute(query)
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Документ '{doc_id}' не знайдено в '{doctype_name}'",
            )

        doc = dict(row._mapping)
        for k, v in doc.items():
            if isinstance(v, datetime):
                doc[k] = v.isoformat()

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
        dt_check = await doctype_registry.get(doctype_name)
        if dt_check.is_virtual:
            return await self._virtual_update(dt_check, doctype_name, user, doc_id, data)

        if doctype_registry.is_system(doctype_name) and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' is managed by the system. Please use the appropriate API.",
            )
        dt = await doctype_registry.get(doctype_name)
        table = compile_doctype_to_table(dt)

        # Ensure document exists
        existing = await self.get_document(doctype_name, doc_id, user)

        # Validate partial
        errors = self._validate_data(dt, data, partial=True)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=errors,
            )

        # Strip protected fields from user data
        update_data: dict[str, Any] = {}
        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
            if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                update_data[field.fieldname] = self._coerce_value(data[field.fieldname], field.fieldtype)

        update_data["modified_at"] = datetime.now(timezone.utc)
        update_data["modified_by"] = user.email

        real_id = existing["id"]
        merged = {**existing, **update_data}

        # Custom Controller Hooks
        _tokens = self._set_grunt_context(user)
        try:
            controller_cls = document_registry.get(doctype_name)
            logger.debug("document.controller_resolved", doctype=doctype_name, controller=controller_cls.__name__)
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

            result = await self.get_document(doctype_name, real_id, user)

            # Create version record if track_changes is enabled
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
                except Exception:  # noqa: BLE001
                    logger.exception("version.create_error", doctype=doctype_name, doc_id=real_id)

            doc.data = result  # refresh with actual data after save
            try:
                await doc.after_save()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("after_update", doctype=doctype_name, doc=result, user=user, session=self.session)
            await fire("after_save", doctype=doctype_name, doc=result, user=user, session=self.session)
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
        dt_check = await doctype_registry.get(doctype_name)
        if dt_check.is_virtual:
            await self._virtual_delete(dt_check, doctype_name, user, doc_id)
            return

        if doctype_registry.is_system(doctype_name) and not user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' is managed by the system. Please use the appropriate API.",
            )
        dt = await doctype_registry.get(doctype_name)
        table = compile_doctype_to_table(dt)

        existing = await self.get_document(doctype_name, doc_id, user)

        if dt.is_submittable and existing.get("docstatus") == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Спочатку скасуйте документ перед видаленням",
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
            logger.info("document.deleted", doctype=doctype_name, id=real_id)

            try:
                await doc.after_delete()
            except GruntError as e:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e

            await fire("after_delete", doctype=doctype_name, doc_id=real_id, user=user, session=self.session)
        finally:
            self._reset_grunt_context(_tokens)

    # ── Type coercion ────────────────────────────────────────────────────

    @staticmethod
    def _coerce_value(value: Any, fieldtype: str) -> Any:
        """Convert string values to proper Python types for SQLAlchemy."""
        # Check fields always coerce to bool — never store NULL
        if fieldtype == "Check":
            if value is None or value == "":
                return False
            return bool(value)
        if value is None or value == "":
            return None if fieldtype in ("Date", "Datetime", "Time", "Int", "Float") else value
        if fieldtype == "Date" and isinstance(value, str):
            return date.fromisoformat(value)
        if fieldtype == "Datetime" and isinstance(value, str):
            return datetime.fromisoformat(value)
        if fieldtype == "Time" and isinstance(value, str):
            return time.fromisoformat(value)
        if fieldtype == "Int" and isinstance(value, str):
            return int(value)
        if fieldtype == "Float" and isinstance(value, str):
            return float(value)
        return value

    # ── Validation ────────────────────────────────────────────────────────

    def _validate_data(
        self, doctype: DocType, data: dict[str, Any], partial: bool = False
    ) -> list[str]:
        errors: list[str] = []
        for field in doctype.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue

            value = data.get(field.fieldname)

            # Required check (skip for partial updates if field not provided)
            if field.required and not partial:
                if value is None or value == "":
                    errors.append(f"{field.fieldname}: Поле '{field.label}' є обов'язковим")

        return errors

    # ── Filter builder ────────────────────────────────────────────────────

    def _apply_filters(self, query, table, filters: dict[str, str]):
        for key, value in filters.items():
            if "__" in key:
                fieldname, op = key.rsplit("__", 1)
            else:
                fieldname, op = key, "eq"

            col = table.c.get(fieldname)
            if col is None:
                continue

            if op == "eq":
                query = query.where(col == value)
            elif op == "gte":
                query = query.where(col >= value)
            elif op == "lte":
                query = query.where(col <= value)
            elif op == "gt":
                query = query.where(col > value)
            elif op == "lt":
                query = query.where(col < value)
            elif op == "like":
                query = query.where(col.like(f"%{value}%"))
            elif op == "ilike":
                query = query.where(col.ilike(f"%{value}%"))
            elif op == "in":
                query = query.where(col.in_(value.split(",")))
            elif op == "isnull":
                if value.lower() in ("true", "1"):
                    query = query.where(col.is_(None))
                else:
                    query = query.where(col.isnot(None))

        return query

    # ── Search ────────────────────────────────────────────────────────────

    def _apply_search(self, query, table, dt: DocType, search: str):
        search_cols = []
        if dt.search_fields:
            for fname in dt.search_fields:
                col = table.c.get(fname)
                if col is not None:
                    search_cols.append(col)
        if not search_cols:
            search_cols = [table.c.name]

        conditions = [col.ilike(f"%{search}%") for col in search_cols]
        from sqlalchemy import or_

        return query.where(or_(*conditions))

    # ── Virtual DocType delegation ──────────────────────────────────────

    def _get_virtual_controller(self, doctype_name: str, user: GruntUser):
        """Get the VirtualDocType controller instance for a virtual DocType."""
        from grunt.core.metadata.virtual import VirtualDocType  # noqa: PLC0415

        controller_cls = document_registry.get(doctype_name)
        # Check if it's a VirtualDocType subclass
        if issubclass(controller_cls, VirtualDocType):
            return controller_cls(doctype_name, user)
        # Fallback — create a base VirtualDocType (will raise NotImplementedError)
        return VirtualDocType(doctype_name, user)

    async def _virtual_list(self, dt, doctype_name, user, page, per_page, sort_by, sort_order, filters, search):
        ctrl = self._get_virtual_controller(doctype_name, user)
        return await ctrl.get_list(
            filters=filters, page=page, per_page=per_page,
            sort_by=sort_by, sort_order=sort_order, search=search,
        )

    async def _virtual_get(self, dt, doctype_name, user, doc_id):
        ctrl = self._get_virtual_controller(doctype_name, user)
        return await ctrl.get(doc_id)

    async def _virtual_create(self, dt, doctype_name, user, data):
        ctrl = self._get_virtual_controller(doctype_name, user)
        return await ctrl.create(data)

    async def _virtual_update(self, dt, doctype_name, user, doc_id, data):
        ctrl = self._get_virtual_controller(doctype_name, user)
        return await ctrl.update(doc_id, data)

    async def _virtual_delete(self, dt, doctype_name, user, doc_id):
        ctrl = self._get_virtual_controller(doctype_name, user)
        return await ctrl.delete(doc_id)

    # ── Autoname (delegated to NamingService) ────────────────────────────
