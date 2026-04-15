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

    from grunt.core.auth.models import User
    from grunt.core.document.multi_link import MultiLinkService


from grunt.core.document.query import _apply_filters, _apply_search
from grunt.core.document.relations import (
    _get_multi_link_fields,
    _load_child_tables,
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
    ) -> dict[str, Any]:
        dt = await doctype_registry.get(doctype_name)

        # Virtual DocType — delegate to sub-module
        if dt.is_virtual:
            return await _virtual_list(
                doctype_name, user, page, per_page, sort_by, sort_order, filters, search
            )

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

        return {
            "data": rows,
            "meta": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if per_page else 1,
            },
        }

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

        query = select(table).where((table.c.id == doc_id) | (table.c.name == doc_id))
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


async def _resolve_link_labels(
    session: AsyncSession,
    dt: Any,
    rows: list[dict[str, Any]],
) -> None:
    """Inject ``fieldname__label`` (and extra display fields) for Link fields.

    For each Link field present in the rows:
    - Injects ``{fieldname}__label`` — the title_field of the linked record.
    - Injects ``{fieldname}__color`` / ``{fieldname}__icon`` if the linked
      DocType has ``color`` / ``icon`` fields (used by MapView, etc.).
    """
    if not rows:
        return

    from sqlalchemy import or_  # noqa: PLC0415

    # Extra field names to inject in addition to __label when available
    _EXTRA_INJECT = ("color", "icon")

    link_fields = [f for f in dt.fields if f.fieldtype == "Link" and f.options]

    # Only process fields that are actually in the result rows
    present_keys = set(rows[0].keys())
    link_fields = [f for f in link_fields if f.fieldname in present_keys]

    if not link_fields:
        return

    for lf in link_fields:
        target_name = lf.options
        try:
            target_dt = await doctype_registry.get(target_name)
        except Exception:  # noqa: BLE001
            continue

        title_field = getattr(target_dt, "title_field", "name") or "name"
        target_table = compile_doctype_to_table(target_dt)

        # Collect unique non-null raw values from rows
        raw_ids: set[str] = {
            str(row[lf.fieldname])
            for row in rows
            if row.get(lf.fieldname) not in (None, "")
        }
        if not raw_ids:
            continue

        # Batch-fetch id + name + title_field from linked table
        cols_to_fetch = [target_table.c.id, target_table.c.name]
        if title_field != "name" and title_field in target_table.c:
            cols_to_fetch.append(target_table.c[title_field])

        # Include extra display fields if the linked DocType has them
        linked_field_names = {f.fieldname for f in target_dt.fields}
        extra_to_fetch = [
            fname for fname in _EXTRA_INJECT
            if fname in linked_field_names and fname in target_table.c
        ]
        for fname in extra_to_fetch:
            cols_to_fetch.append(target_table.c[fname])

        q = (
            select(*cols_to_fetch)
            .where(or_(target_table.c.id.in_(raw_ids), target_table.c.name.in_(raw_ids)))
        )

        # Use a savepoint so a failed query (e.g. table doesn't exist) doesn't
        # corrupt the outer session state.
        try:
            async with session.begin_nested():
                result = await session.execute(q)
                linked_rows = result.mappings().all()
        except Exception:  # noqa: BLE001
            continue

        # Build lookup: raw_id/name → label + extra fields
        label_map: dict[str, str] = {}
        extra_maps: dict[str, dict[str, Any]] = {fname: {} for fname in extra_to_fetch}

        for lr in linked_rows:
            label = str(lr.get(title_field) or lr.get("name") or "")
            for key in (str(lr["id"]), str(lr["name"])):
                label_map[key] = label
                for fname in extra_to_fetch:
                    val = lr.get(fname)
                    if val is not None:
                        extra_maps[fname][key] = val

        # Inject into each row
        label_key = f"{lf.fieldname}__label"
        for row in rows:
            raw = row.get(lf.fieldname)
            if raw not in (None, ""):
                raw_str = str(raw)
                row[label_key] = label_map.get(raw_str, raw_str)
                for fname in extra_to_fetch:
                    val = extra_maps[fname].get(raw_str)
                    if val is not None:
                        row[f"{lf.fieldname}__{fname}"] = val
