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
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.models import GruntUser
from grunt.core.metadata.compiler import compile_doctype_to_table, get_table_name
from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
from grunt.core.metadata.registry import doctype_registry
from grunt.core.hooks import fire
from grunt.core.metadata.system_doctypes import is_system_doctype

logger = structlog.get_logger()

# Fields that users may never set or overwrite
PROTECTED_FIELDS = frozenset({"id", "owner", "created_at", "docstatus"})


class DocumentService:
    """Dynamic CRUD for any registered DocType."""

    def __init__(self, session: AsyncSession, engine: AsyncEngine) -> None:
        self.session = session
        self.engine = engine

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
        table = compile_doctype_to_table(dt)

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
        if is_system_doctype(doctype_name):
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

        row = {
            "id": doc_id,
            "name": self._apply_autoname(dt, data) or doc_id[:8],
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

        await fire("before_save", doctype=doctype_name, doc=row, user=user, session=self.session)

        await self.session.execute(table.insert().values(**row))
        await self.session.flush()

        logger.info("document.created", doctype=doctype_name, id=doc_id)

        await fire("after_save", doctype=doctype_name, doc=row, user=user, session=self.session)

        # Serialise datetimes for response
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.isoformat()

        return row

    # ── Get ────────────────────────────────────────────────────────────

    async def get_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: GruntUser,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
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
        return doc

    # ── Update ────────────────────────────────────────────────────────────

    async def update_document(
        self,
        doctype_name: str,
        doc_id: str,
        data: dict[str, Any],
        user: GruntUser,
    ) -> dict[str, Any]:
        if is_system_doctype(doctype_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' керується системою. Використовуйте відповідний API.",
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
        await fire("before_save", doctype=doctype_name, doc=merged, user=user, session=self.session)

        await self.session.execute(
            table.update().where(table.c.id == real_id).values(**update_data)
        )
        await self.session.flush()

        logger.info("document.updated", doctype=doctype_name, id=real_id)

        result = await self.get_document(doctype_name, real_id, user)
        await fire("after_save", doctype=doctype_name, doc=result, user=user, session=self.session)
        return result

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: GruntUser,
    ) -> None:
        if is_system_doctype(doctype_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{doctype_name}' керується системою. Використовуйте відповідний API.",
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
        await fire("before_delete", doctype=doctype_name, doc=existing, user=user, session=self.session)

        await self.session.execute(table.delete().where(table.c.id == real_id))
        await self.session.flush()
        logger.info("document.deleted", doctype=doctype_name, id=real_id)

        await fire("after_delete", doctype=doctype_name, doc_id=real_id, user=user, session=self.session)

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

    # ── Autoname ──────────────────────────────────────────────────────────

    def _apply_autoname(self, doctype: DocType, data: dict[str, Any]) -> str | None:
        if not doctype.autoname:
            return None
        if doctype.autoname.startswith("field:"):
            field_name = doctype.autoname[6:]
            return str(data.get(field_name, ""))
        # For pattern-based autonaming (e.g. "CONTR-.YYYY.-.####") — simplified
        return None
