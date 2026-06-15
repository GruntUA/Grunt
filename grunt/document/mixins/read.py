"""Mixin classes for DocumentService."""

from __future__ import annotations

import base64
import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.document.base import DocumentList
    from grunt.document.multi_link import MultiLinkService


from grunt.document.formula import evaluate_read_formulas
from grunt.document.query import _apply_filters, _apply_search, _expand_child_of_filters
from grunt.document.relations import (
    _get_multi_link_fields,
    _load_child_tables,
    _resolve_link_labels,
    _table_fieldnames,
)
from grunt.document.virtual import (
    is_virtual_routed,
    virtual_get,
    virtual_list,
)
from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry

logger = structlog.get_logger()

PROTECTED_FIELDS = frozenset({"name", "owner", "created_at", "docstatus"})

_CURSOR_SEP = "||"  # separator unlikely to appear in sort values


def _encode_cursor(sort_val: Any, doc_id: str) -> str:
    """Encode (sort_value, id) into a safe opaque cursor string."""
    sort_str = sort_val.isoformat() if isinstance(sort_val, datetime) else str(sort_val)
    raw = f"{sort_str}{_CURSOR_SEP}{doc_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode cursor → (sort_value_str, doc_id)."""
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    sort_str, doc_id = raw.rsplit(_CURSOR_SEP, 1)
    return sort_str, doc_id


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
        cursor: str | None = None,
    ) -> DocumentList:
        dt = await doctype_registry.get(doctype_name)

        # Virtual DocType or VirtualDocType controller — delegate to sub-module
        if is_virtual_routed(dt, doctype_name):
            return await virtual_list(
                doctype_name, user, page, per_page, sort_by, sort_order, filters, search
            )

        table = compile_doctype_to_table(dt)

        from grunt.document.base import DocumentList

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
        cols: list[Any]
        if fields:
            required = {"name", "modified_at", "docstatus"}
            requested = required | set(fields)
            cols = [table.c[c] for c in requested if c in table.c]
        else:
            cols = [table]

        query = select(*cols)

        # Controller hook: list_filter_extra — DocType controllers may inject
        # extra WHERE clauses (e.g. temporal guards, visibility rules) without
        # modifying the framework core.
        from grunt.document.base import Document
        from grunt.document.registry import document_registry

        controller_cls = document_registry.get(doctype_name)
        extra_clause = None
        if controller_cls.list_filter_extra is not Document.list_filter_extra:
            extra_clause = await controller_cls.list_filter_extra(
                self.session, filters or {}, table
            )
        if extra_clause is not None:
            query = query.where(extra_clause)

        # Expand tree-aware child_of operators before applying filters
        if filters and any(k.endswith("__child_of") for k in filters):
            filters = await _expand_child_of_filters(self.session, dt, filters)

        # Filters
        if filters:
            query = _apply_filters(query, table, filters)

        # Search
        if search:
            query = _apply_search(query, table, dt, search)

        # Count
        count_q = select(func.count()).select_from(table)
        if extra_clause is not None:
            count_q = count_q.where(extra_clause)
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
            from grunt.site.manager import text_sort_expr

            dialect_name = self.session.bind.dialect.name if self.session.bind else "sqlite"
            sort_expr = text_sort_expr(sort_col, dialect_name)
        else:
            sort_expr = sort_col
        if sort_order == "asc":
            query = query.order_by(sort_expr.asc())
        else:
            query = query.order_by(sort_expr.desc())

        # Pagination — cursor mode avoids slow OFFSET on large tables
        if cursor:
            try:
                sort_str, cursor_id = _decode_cursor(cursor)
                # Try to parse as datetime; fall back to raw string
                try:
                    cursor_val: Any = datetime.fromisoformat(sort_str)
                except ValueError:
                    cursor_val = sort_str

                from sqlalchemy import and_, or_

                if sort_order == "asc":
                    keyset = or_(
                        sort_col > cursor_val,
                        and_(sort_col == cursor_val, table.c.name > cursor_id),
                    )
                else:
                    keyset = or_(
                        sort_col < cursor_val,
                        and_(sort_col == cursor_val, table.c.name < cursor_id),
                    )
                query = query.where(keyset)
            except Exception:
                logger.warning("list_documents.invalid_cursor", cursor=cursor)

        query = query.limit(per_page)
        if not cursor:
            query = query.offset((page - 1) * per_page)

        result = await self.session.execute(query)
        rows: list[dict[Any, Any]] = [dict(r._mapping) for r in result]

        # Resolve Link field labels (inject fieldname__label into each row)
        try:
            await _resolve_link_labels(self.session, dt, rows)
        except Exception as _lbl_err:
            logger.warning(
                "list_documents.link_labels_failed", doctype=doctype_name, error=str(_lbl_err)
            )

        # Serialise datetimes and evaluate read formulas
        for doc_row in rows:
            for k, v in doc_row.items():
                if isinstance(v, datetime):
                    doc_row[k] = v.isoformat()
            await evaluate_read_formulas(dt, doc_row)

        next_cursor: str | None = None
        if rows and len(rows) == per_page:
            last = rows[-1]
            sort_raw = last.get(sort_by)
            last_id = str(last.get("name", ""))
            if sort_raw is not None and last_id:
                next_cursor = _encode_cursor(sort_raw, last_id)

        return DocumentList(
            data=rows,
            meta={
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
                "next_cursor": next_cursor,
            },
        )

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

        table = compile_doctype_to_table(dt)

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

        table_fields = _table_fieldnames(dt)
        ml_fields = {f.fieldname for f in _get_multi_link_fields(dt)}

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
            if load_all_relations:
                ml_data = await self._ml.get_all_for_doc(doctype_name, doc["name"])
                for fieldname in ml_fields:
                    doc[fieldname] = ml_data.get(fieldname, [])
            else:
                selected_ml = sorted(ml_fields & expand_set)
                if selected_ml:
                    ml_data = await self._ml.get_all_for_doc(doctype_name, doc["name"])
                    for fieldname in selected_ml:
                        doc[fieldname] = ml_data.get(fieldname, [])

        await evaluate_read_formulas(dt, doc)

        # Call controller on_load if the app overrides it
        from grunt.document.base import Document
        from grunt.document.registry import document_registry

        controller_cls = document_registry.get(doctype_name)
        if controller_cls.on_load is not Document.on_load:
            controller = controller_cls(doctype_name, doc, user, self.session)
            await controller.on_load()

        return doc
