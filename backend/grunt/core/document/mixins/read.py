"""Mixin classes for DocumentService."""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.doctypes.user.user import User
    from grunt.core.document.base import DocumentList
    from grunt.core.document.multi_link import MultiLinkService


from grunt.core.document.query import _apply_filters, _apply_search
from grunt.core.document.relations import (
    _EXTRA_INJECT,
    _get_multi_link_fields,
    _load_child_tables,
    _resolve_link_labels,
)
from grunt.core.document.virtual import (
    _virtual_get,
    _virtual_list,
)
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

PROTECTED_FIELDS = frozenset({"id", "owner", "created_at", "docstatus"})


class DocumentReadMixin:
    session: AsyncSession
    _ml: MultiLinkService

    # ── List ──────────────────────────────────────────────────────────────

    async def list_documents(
        self,
        doctype_name: str,
        user: User,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "modified_at",
        sort_order: str = "desc",
        filters: dict[str, str] | None = None,
        search: str | None = None,
        fields: list[str] | None = None,
    ) -> DocumentList:
        dt = await doctype_registry.get(doctype_name)

        # Virtual DocType — delegate to sub-module
        if dt.is_virtual:
            return await _virtual_list(
                doctype_name, user, page, per_page, sort_by, sort_order, filters, search
            )

        table = compile_doctype_to_table(dt)

        from grunt.core.document.base import DocumentList  # noqa: PLC0415

        # Singleton — return at most 1 row, ignore pagination
        if dt.is_singleton:
            result = await self.session.execute(select(table).limit(1))
            row = result.first()
            data_list = [dict(row._mapping)] if row else []
            for r in data_list:
                for k, v in r.items():
                    if isinstance(v, datetime):
                        r[k] = v.isoformat()
            return DocumentList(
                data=data_list,
                meta={"total": len(data_list), "page": 1, "per_page": 1, "pages": 1},
            )

        # Select columns
        # ... (lines 79-153 unchanged logic) ...
        # (Assuming the logic above remains the same until the final return)

        # ... (skipping some lines for conciseness in replacement chunk) ...
        # I'll replace the last return as well.

        # Select columns
        cols: list[Any]
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
        text_types = {"TEXT", "VARCHAR", "CHAR", "CLOB", "STRING", "NVARCHAR", "NCHAR"}
        col_type = str(sort_col.type).upper()
        is_text = any(t in col_type for t in text_types)
        if is_text:
            from grunt.core.site.manager import text_sort_expr  # noqa: PLC0415

            dialect_name = self.session.bind.dialect.name if self.session.bind else "sqlite"
            sort_expr = text_sort_expr(sort_col, dialect_name)
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
        rows: list[dict[Any, Any]] = [dict(r._mapping) for r in result]

        # Resolve Link field labels (inject fieldname__label into each row)
        try:
            await _resolve_link_labels(self.session, dt, rows)
        except Exception as _lbl_err:  # noqa: BLE001
            logger.warning(
                "list_documents.link_labels_failed", doctype=doctype_name, error=str(_lbl_err)
            )

        # Serialise datetimes
        for doc_row in rows:
            for k, v in doc_row.items():
                if isinstance(v, datetime):
                    doc_row[k] = v.isoformat()

        # Apply field-level permissions
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        hidden = permission_checker.hidden_fields(user, dt)
        if hidden:
            for doc_row in rows:
                for field in hidden:
                    doc_row.pop(field, None)

        return DocumentList(
            data=rows,
            meta={
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
            },
        )

    # ── Get ────────────────────────────────────────────────────────────

    async def get_document(
        self,
        doctype_name: str,
        doc_id: str,
        user: User,
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)
        if dt.is_virtual:
            return await _virtual_get(doctype_name, user, doc_id)

        table = compile_doctype_to_table(dt)

        result = await self.session.execute(select(table).where(table.c.id == doc_id))
        row = result.first()
        if row is None:
            result = await self.session.execute(select(table).where(table.c.name == doc_id))
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
