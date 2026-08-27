"""Collection-level document operations.

Frappe-aligned module functions that act on *sets* of documents (list, bulk
delete) or cross-document concerns (rename cascade) rather than a single
stateful document. Single-document CRUD lives on
:class:`~grunt.document.base.Document`.
"""

from __future__ import annotations

import base64
import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select, update

from grunt.db.api import _apply_filters
from grunt.document.base import Document, DocumentList
from grunt.document.formula import evaluate_read_formulas
from grunt.document.meta import Meta
from grunt.document.query import _apply_search, _expand_child_of_filters
from grunt.document.registry import document_registry
from grunt.document.relations import _resolve_attach_labels, _resolve_link_labels
from grunt.document.serde import serialize_datetimes
from grunt.document.update_side_effects import (
    bulk_delete_virtual,
    collect_bulk_delete_candidates,
    run_bulk_after_delete_hooks,
    run_bulk_before_delete_hooks,
    run_bulk_delete_writes,
)
from grunt.document.virtual import is_virtual_routed, virtual_list
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User

logger = structlog.get_logger()

_CURSOR_SEP = "||"  # separator unlikely to appear in sort values

_TEXT_SQL_TYPES = frozenset({"TEXT", "VARCHAR", "CHAR", "CLOB", "STRING", "NVARCHAR", "NCHAR"})


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


# ── List ──────────────────────────────────────────────────────────────────


async def _list_singleton(session: AsyncSession, table: Any) -> DocumentList:
    """Return the (at most one) row of a singleton DocType, ignoring pagination."""
    result = await session.execute(select(table).limit(1))
    row = result.first()
    data_list = [dict(row._mapping)] if row else []
    for r in data_list:
        serialize_datetimes(r)
    return DocumentList(
        data=data_list,
        meta={"total": len(data_list), "page": 1, "per_page": 1, "pages": 1},
    )


def _select_columns(table: Any, fields: list[str] | None) -> list[Any]:
    """Return the SQLAlchemy column list for a list query.

    Always includes ``name``/``modified_at``/``docstatus`` even when *fields*
    is a restricted subset — callers (list views, sorting) rely on them.
    """
    if not fields:
        return [table]
    required = {"name", "modified_at", "docstatus"}
    requested = required | set(fields)
    return [table.c[c] for c in requested if c in table.c]


async def _resolve_list_filter_extra(
    session: AsyncSession,
    doctype_name: str,
    filters: dict[str, str] | None,
    table: Any,
) -> Any | None:
    """Return the controller's ``list_filter_extra`` WHERE clause, if overridden."""
    controller_cls = document_registry.get(doctype_name)
    if controller_cls.list_filter_extra is Document.list_filter_extra:
        return None
    return await controller_cls.list_filter_extra(session, filters or {}, table)


def _apply_where(
    query: Any,
    table: Any,
    dt: Any,
    filters: dict[str, str] | None,
    search: str | None,
    extra_clause: Any | None,
    user: Any,
) -> Any:
    """Apply row-level permissions, the controller clause, filters, and search.

    Shared by the data query and the COUNT query so the two can never drift
    out of sync with each other — including which rows count() reports as
    the pagination total.
    """
    from grunt.permissions.query import apply_permission_filter

    query = apply_permission_filter(query, table, user, dt)
    if extra_clause is not None:
        query = query.where(extra_clause)
    if filters:
        query = _apply_filters(query, table, filters)
    if search:
        query = _apply_search(query, table, dt, search)
    return query


def _resolve_sort(
    session: AsyncSession, table: Any, sort_by: str, sort_order: str
) -> tuple[Any, Any]:
    """Return ``(sort_col, order_by_expr)`` for the requested sort field.

    Text-typed columns get a dialect-aware collation (``text_sort_expr``) so
    sorting is locale-correct; other types sort on the raw column.
    """
    sort_col = table.c.get(sort_by, table.c.modified_at)
    col_type = str(sort_col.type).upper()
    if any(t in col_type for t in _TEXT_SQL_TYPES):
        from grunt.site.manager import text_sort_expr

        dialect_name = session.bind.dialect.name if session.bind else "sqlite"
        sort_expr = text_sort_expr(sort_col, dialect_name)
    else:
        sort_expr = sort_col
    order_by_expr = sort_expr.asc() if sort_order == "asc" else sort_expr.desc()
    return sort_col, order_by_expr


def _apply_pagination(
    query: Any,
    table: Any,
    sort_col: Any,
    sort_order: str,
    cursor: str | None,
    page: int,
    per_page: int,
) -> Any:
    """Apply cursor (keyset) or offset pagination to *query*.

    Cursor mode avoids a slow OFFSET scan on large tables; an invalid cursor
    is logged and ignored (falls back to an unfiltered first page).
    """
    if cursor:
        try:
            sort_str, cursor_id = _decode_cursor(cursor)
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
    return query


async def _finalize_rows(
    session: AsyncSession, dt: Any, doctype_name: str, rows: list[dict[Any, Any]]
) -> None:
    """Resolve Link labels, serialise datetimes, and evaluate read formulas in place."""
    try:
        await _resolve_link_labels(session, dt, rows)
    except Exception as exc:
        logger.warning(
            "list_documents.link_labels_failed", doctype=doctype_name, error=str(exc)
        )

    try:
        await _resolve_attach_labels(session, dt, rows)
    except Exception as exc:
        logger.warning(
            "list_documents.attach_labels_failed", doctype=doctype_name, error=str(exc)
        )

    for doc_row in rows:
        serialize_datetimes(doc_row)
        await evaluate_read_formulas(dt, doc_row)


def _build_next_cursor(rows: list[dict[Any, Any]], per_page: int, sort_by: str) -> str | None:
    """Return an opaque cursor for the page after *rows*, or ``None`` if this was the last page."""
    if not rows or len(rows) != per_page:
        return None
    last = rows[-1]
    sort_raw = last.get(sort_by)
    last_id = str(last.get("name", ""))
    if sort_raw is not None and last_id:
        return _encode_cursor(sort_raw, last_id)
    return None


async def list_documents(
    session: AsyncSession,
    doctype_name: str,
    user: User,
    *,
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

    table = Meta(dt).table

    # Singleton — return at most 1 row, ignore pagination
    if dt.is_singleton:
        return await _list_singleton(session, table)

    query = select(*_select_columns(table, fields))

    # Controller hook: list_filter_extra — DocType controllers may inject
    # extra WHERE clauses (e.g. temporal guards, visibility rules) without
    # modifying the framework core.
    extra_clause = await _resolve_list_filter_extra(session, doctype_name, filters, table)

    # Expand tree-aware child_of operators before applying filters
    if filters and any(k.endswith("__child_of") for k in filters):
        filters = await _expand_child_of_filters(session, dt, filters)

    query = _apply_where(query, table, dt, filters, search, extra_clause, user)

    count_q = _apply_where(
        select(func.count()).select_from(table), table, dt, filters, search, extra_clause, user
    )
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0

    sort_col, order_by_expr = _resolve_sort(session, table, sort_by, sort_order)
    query = query.order_by(order_by_expr)
    query = _apply_pagination(query, table, sort_col, sort_order, cursor, page, per_page)

    result = await session.execute(query)
    rows: list[dict[Any, Any]] = [dict(r._mapping) for r in result]

    await _finalize_rows(session, dt, doctype_name, rows)
    next_cursor = _build_next_cursor(rows, per_page, sort_by)

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


# ── Bulk delete ─────────────────────────────────────────────────────────────


async def bulk_delete(
    session: AsyncSession,
    engine: AsyncEngine,
    doctype_name: str,
    ids: list[str],
    user: User,
    *,
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

    from grunt.app import grunt as _grunt
    from grunt.document.multi_link import MultiLinkService

    dt = await doctype_registry.get(doctype_name)

    if is_virtual_routed(dt, doctype_name):
        return await bulk_delete_virtual(doctype_name=doctype_name, ids=ids, user=user)

    table = Meta(dt).table
    ml = MultiLinkService(session)
    to_delete, errors = await collect_bulk_delete_candidates(
        session=session, dt=dt, table=table, ids=ids
    )

    if not to_delete:
        return 0, errors

    total = len(ids)

    async def _report(done: int) -> None:
        if progress_cb is not None:
            await progress_cb(done, total, len(errors))

    tokens = _grunt.set_context(session=session, engine=engine, user=user)
    try:
        controllers = await run_bulk_before_delete_hooks(
            doctype_name=doctype_name,
            docs=to_delete,
            user=user,
            session=session,
            errors=errors,
            report=_report,
        )
    finally:
        _grunt.reset_context(tokens)

    if not controllers:
        return 0, errors

    final_ids = [str(d["name"]) for d, _ in controllers]

    tokens = _grunt.set_context(session=session, engine=engine, user=user)
    try:
        await run_bulk_delete_writes(
            session=session,
            ml=ml,
            table=table,
            doctype_name=doctype_name,
            final_ids=final_ids,
        )
        await run_bulk_after_delete_hooks(
            session=session,
            doctype_name=doctype_name,
            controllers=controllers,
            errors=errors,
        )
    finally:
        _grunt.reset_context(tokens)

    deleted = len(final_ids)
    await _report(total)
    return deleted, errors


# ── Rename ──────────────────────────────────────────────────────────────────


async def _rename_child_and_link_refs(
    session: AsyncSession,
    dt_meta: Meta,
    doctype_name: str,
    old_id: str,
    new_id: str,
) -> None:
    """Update every other DocType's child-table parent_name and Link field values."""
    all_dts = await doctype_registry.list_all()
    for other_dt in all_dts:
        other_meta = Meta(other_dt)

        is_child = any(f.options == other_dt.name for f in dt_meta.get_child_table_fields())
        if is_child:
            child_table = other_meta.table
            await session.execute(
                child_table.update()
                .where(child_table.c.parent_name == old_id)
                .values(parent_name=new_id)
            )

        for f in other_meta.get_link_fields():
            if f.fieldtype == "Link" and f.options == doctype_name:
                ref_table = other_meta.table
                await session.execute(
                    ref_table.update()
                    .where(ref_table.c[f.fieldname] == old_id)
                    .values(**{f.fieldname: new_id})
                )


async def _rename_multilink_refs(
    session: AsyncSession, doctype_name: str, old_id: str, new_id: str
) -> None:
    """Update grunt_core_multi_link rows where *old_id* is either side of the link."""
    from grunt.metadata.compiler import MULTI_LINK_TABLE

    await session.execute(
        update(MULTI_LINK_TABLE)
        .where(
            MULTI_LINK_TABLE.c.parent_name == old_id,
            MULTI_LINK_TABLE.c.parent_doctype == doctype_name,
        )
        .values(parent_name=new_id)
    )
    await session.execute(
        update(MULTI_LINK_TABLE)
        .where(
            MULTI_LINK_TABLE.c.link_name == old_id,
            MULTI_LINK_TABLE.c.link_doctype == doctype_name,
        )
        .values(link_name=new_id)
    )


# System DocTypes that reference a document by id via a hardcoded field name
# (not a declared Link field, so _rename_child_and_link_refs can't find them).
_RENAME_SYSTEM_REFS = [
    ("ActivityLog", "doc_id"),
    ("DocVersion", "doc_id"),
    ("File", "doc_id"),
    ("File", "attached_to_id"),
    ("Comment", "reference_id"),
    ("EmailQueue", "doc_id"),
]


async def _rename_system_refs(session: AsyncSession, old_id: str, new_id: str) -> None:
    """Best-effort update of _RENAME_SYSTEM_REFS rows pointing at *old_id*."""
    for sys_dt_name, sys_fieldname in _RENAME_SYSTEM_REFS:
        try:
            sys_dt = await doctype_registry.get(sys_dt_name)
            sys_table = Meta(sys_dt).table
            if sys_fieldname in sys_table.c:
                await session.execute(
                    sys_table.update()
                    .where(sys_table.c[sys_fieldname] == old_id)
                    .values(**{sys_fieldname: new_id})
                )
        except Exception as exc:
            logger.warning(
                "document.rename_system_ref_failed",
                doctype=sys_dt_name,
                field=sys_fieldname,
                error=str(exc),
            )
            continue


async def rename_document(
    session: AsyncSession,
    engine: AsyncEngine,
    doctype_name: str,
    old_id: str,
    new_id: str,
    user: User,
) -> dict[str, Any]:
    """Update the primary ID of a document and cascade changes to all references."""

    async def _load(doc_id: str) -> dict[str, Any]:
        doc = await Document.load(doctype_name, doc_id, session=session, engine=engine, user=user)
        return doc.as_dict()

    if old_id == new_id:
        return await _load(old_id)

    dt = await doctype_registry.get(doctype_name)
    if is_virtual_routed(dt, doctype_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rename virtual documents",
        )

    dt_meta = Meta(dt)
    table = dt_meta.table

    exists_q = select(table.c.name).where(table.c.name == new_id)
    exists_res = await session.execute(exists_q)
    if exists_res.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document with name '{new_id}' already exists",
        )

    await session.execute(table.update().where(table.c.name == old_id).values(name=new_id))

    await _rename_child_and_link_refs(session, dt_meta, doctype_name, old_id, new_id)
    await _rename_multilink_refs(session, doctype_name, old_id, new_id)
    await _rename_system_refs(session, old_id, new_id)

    await session.flush()

    # Update search index: delete old, re-index under the new id.
    from grunt.search.service import search_index_service

    await search_index_service.remove_document(session, doctype_name, old_id)
    new_doc = await _load(new_id)
    await search_index_service.index_document(session, doctype_name, dt, new_doc)

    logger.info("document.renamed", doctype=doctype_name, old=old_id, new=new_id)
    return new_doc
