"""Collection-level document operations.

Module functions that act on *sets* of documents (list, bulk delete) or
cross-document concerns (rename cascade) rather than a single stateful
document. Single-document CRUD lives on
:class:`~grunt.document.base.Document`.
"""

import base64
import json
import math
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import grunt
from grunt import _, log
from grunt.document.base import (
    Document,
    DocumentList,
    load_document,
)
from grunt.document.formula import evaluate_read_formulas
from grunt.document.meta import Meta
from grunt.document.multi_link import MultiLinkService
from grunt.document.query import expand_child_of_filters
from grunt.document.registry import document_registry
from grunt.document.relations import _resolve_attach_labels, _resolve_link_labels
from grunt.document.serde import serialize_datetimes
from grunt.document.update_side_effects import (
    bulk_delete_one_by_one,
    collect_bulk_delete_candidates,
    run_bulk_after_delete_hooks,
    run_bulk_before_delete_hooks,
    run_bulk_delete_writes,
)
from grunt.errors import unprocessable
from grunt.local import _user_ctx
from grunt.metadata.compiler import MULTI_LINK_TABLE
from grunt.metadata.registry import doctype_registry
from grunt.permissions.query import read_predicate
from grunt.query import nodes as q
from grunt.query import run
from grunt.query.query import Query, Sort
from grunt.query.sql import filter_expr, where
from grunt.search.service import search_index_service
from grunt.store import BULK, REFERENCES, SQL, Unavailable, store_for, supports


def _encode_cursor(sort_val: Any, doc_id: str) -> str:
    """Encode (sort_value, id) into an opaque cursor; the value keeps its JSON type
    (a number stays a number, NULL stays NULL)."""
    raw = json.dumps([sort_val, doc_id], default=str, ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[Any, str]:
    """Decode a cursor -> (sort_value, doc_id)."""
    sort_val, doc_id = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return sort_val, str(doc_id)


# List


async def _resolve_list_filter_extra(
    session: AsyncSession,
    dt: Any,
    filters: dict[str, str] | None,
) -> q.Expr:
    """The controller's ``list_filter_extra`` clause as a ``Raw`` node (``TRUE``
    when it has none) - a SQL condition, so only a table's list takes one."""
    hook = document_registry.get(dt.name).list_filter_extra
    if hook.__func__ is Document.list_filter_extra.__func__ or not supports(dt, SQL):
        return q.TRUE
    clause = await hook(session, filters or {}, dt.table)
    return q.TRUE if clause is None else q.Raw(clause)


async def _list_where(session: AsyncSession, dt: Any, filters: dict[str, Any] | None) -> q.Expr:
    """The filters of a list (``__child_of`` expanded) and the controller's
    ``list_filter_extra`` - one predicate for the page and its total."""
    extra = await _resolve_list_filter_extra(session, dt, filters)
    if filters and any(k.endswith("__child_of") for k in filters):
        filters = await expand_child_of_filters(session, dt.doc, filters)
    return q.and_(filter_expr(filters, dt.columns, dt), extra)


async def _finalize_rows(
    session: AsyncSession, dt: Any, doctype_name: str, rows: list[dict[Any, Any]]
) -> None:
    """Resolve Link labels, serialise datetimes, and evaluate read formulas in place."""
    try:
        await _resolve_link_labels(session, dt, rows)
    except Exception as exc:
        log.warning("list_documents.link_labels_failed", doctype=doctype_name, error=str(exc))

    try:
        await _resolve_attach_labels(session, dt, rows)
    except Exception as exc:
        log.warning("list_documents.attach_labels_failed", doctype=doctype_name, error=str(exc))

    raw_dt = dt.doc
    for doc_row in rows:
        serialize_datetimes(doc_row)
        await evaluate_read_formulas(raw_dt, doc_row)


def _build_next_cursor(rows: list[dict[Any, Any]], per_page: int, sort_by: str) -> str | None:
    """Return an opaque cursor for the page after *rows*, or ``None`` if this was the last page."""
    if not rows or len(rows) != per_page:
        return None
    last = rows[-1]
    last_id = str(last.get("name", ""))
    if not last_id or (sort_by != "name" and sort_by not in last):
        return None  # the sort value isn't in the rows (not among *fields*)
    return _encode_cursor(last.get(sort_by), last_id)


async def list_documents(
    session: AsyncSession,
    doctype_name: str,
    user: str,
    *,
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "modified_at",
    sort_order: str = "desc",
    filters: dict[str, str] | None = None,
    search: str | None = None,
    fields: list[str] | None = None,
    cursor: str | None = None,
    include_total: bool = True,
) -> DocumentList:
    """A page of the documents of *doctype_name* the *user* may see, from its
    store - filtered, searched, sorted; with Link labels and read formulas."""
    dt = await _require_meta(doctype_name)

    # Singleton - at most one row, pagination ignored.
    if dt.is_singleton:
        rows = await run.fetch(
            Query(doctype_name, limit=1), ignore_permissions=True, session=session
        )
        for r in rows:
            serialize_datetimes(r)
        return DocumentList(
            data=rows, meta={"total": len(rows), "page": 1, "per_page": 1, "pages": 1}
        )

    after: tuple[Any, str] | None = None
    if cursor:
        try:
            after = _decode_cursor(cursor)
        except Exception:
            log.warning("list_documents.invalid_cursor", cursor=cursor)

    try:
        sort = Sort.parse(sort_by, sort_order, known=dt.columns)
    except ValueError as e:
        raise unprocessable(str(e)) from None
    query = Query(
        doctype_name,
        where=await _list_where(session, dt, filters),
        # name/modified_at always - list views and the cursor rely on them.
        fields=tuple(dict.fromkeys(["name", "modified_at", *fields])) if fields else None,
        sort=sort,
        limit=per_page,
        offset=(page - 1) * per_page,
        after=after,
        search=search or None,
    )
    try:
        rows, total = await run.page(query, user=user, with_total=include_total, session=session)
    except Unavailable as exc:
        # The source can't be reached - an empty list that says so.
        return DocumentList(
            data=[],
            meta={
                "total": 0,
                "page": page,
                "per_page": per_page,
                "pages": 0,
                "unavailable": True,
                "unavailable_message": str(exc),
            },
        )

    await _finalize_rows(session, dt, doctype_name, rows)
    next_cursor = _build_next_cursor(rows, per_page, sort_by)

    return DocumentList(
        data=rows,
        meta={
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (
                (math.ceil(total / per_page) if per_page else 1) if total is not None else None
            ),
            "next_cursor": next_cursor,
        },
    )


async def count_documents(
    session: AsyncSession,
    doctype_name: str,
    user: str,
    *,
    filters: dict[str, str] | None = None,
    search: str | None = None,
) -> int:
    """Count rows the *user* is allowed to see - the same row-level permission
    filter ``list_documents`` applies to its pagination total, so a sidebar
    badge or a headline stat never reports rows the list itself hides.
    """
    dt = await _require_meta(doctype_name)
    query = Query(dt.name, where=await _list_where(session, dt, filters), search=search or None)
    try:
        return await run.count(query, user=user, session=session)
    except Unavailable:
        return 0


async def _require_meta(doctype_name: str) -> Any:
    dt = await grunt.get_meta(doctype_name)
    if dt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype_name},
        )
    return dt


async def field_years(
    session: AsyncSession,
    doctype_name: str,
    user: str,
    fieldname: str,
) -> list[int]:
    """Distinct calendar years of a Date/Datetime field, newest first, over the
    rows the *user* may see - the options of a year quick filter.

    Under the same row-level permissions as ``count_documents``; the list's own
    filters are not applied, so picking one year doesn't hide the others.
    """
    dt = await grunt.get_meta(doctype_name)
    if dt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype_name},
        )
    field = dt.get_field(fieldname)
    if (
        not supports(dt, SQL)
        or field is None
        or field.fieldtype
        not in (
            "Date",
            "Datetime",
        )
    ):
        return []

    table = dt.table
    col = table.c.get(fieldname)
    if col is None:
        return []
    year = func.extract("year", col)
    predicate = q.and_(
        await read_predicate(user, dt),
        await _resolve_list_filter_extra(session, dt, None),
    )
    query = await where(
        select(year).select_from(table).where(col.is_not(None)).distinct(),
        predicate,
        table,
        doctype_name,
    )
    rows = (await session.execute(query)).scalars().all()
    return sorted({int(y) for y in rows if y is not None}, reverse=True)


# Bulk delete


async def bulk_delete(
    session: AsyncSession,
    engine: AsyncEngine,
    doctype_name: str,
    ids: list[str],
    user: str,
    *,
    replace_with: str | None = None,
    progress_cb: Any | None = None,
) -> tuple[int, list[str]]:
    """Delete multiple documents efficiently in a single transaction.

    Runs per-document hooks (before/after_delete) but batches all DB
    writes (DELETE, multi-link cleanup, search index) into one flush.

    ``replace_with`` - when given, every reference to each deleted id is
    repointed to this surviving document (of the same DocType) before the
    rows are removed.

    ``progress_cb`` is an optional async callable
    ``(done: int, total: int, errors: int) -> None`` called after each
    before_delete hook phase and once after the batch commit.

    Returns ``(deleted_count, error_messages)``.
    """
    if not ids:
        return 0, []

    dt = await grunt.get_meta(doctype_name)
    if dt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype_name},
        )

    if not store_for(dt, session).can(BULK):
        return await bulk_delete_one_by_one(session, engine, doctype_name, ids, user)

    table = dt.table

    if replace_with:
        for src in ids:
            if src == replace_with:
                continue
            await validate_replacement(session, dt, src, replace_with)
            await repoint_references(session, dt, doctype_name, src, replace_with, is_merge=True)
        await session.flush()
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

    tokens = grunt.set_context(session=session, engine=engine, user=_user_ctx.get())
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
        grunt.reset_context(tokens)

    if not controllers:
        return 0, errors

    final_ids = [str(d["name"]) for d, _ in controllers]

    tokens = grunt.set_context(session=session, engine=engine, user=_user_ctx.get())
    try:
        await run_bulk_delete_writes(
            session=session,
            ml=ml,
            dt=dt,
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
        grunt.reset_context(tokens)

    deleted = len(final_ids)
    await _report(total)
    return deleted, errors


# Rename


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
            if f.options == doctype_name:
                ref_table = other_meta.table
                await session.execute(
                    ref_table.update()
                    .where(ref_table.c[f.fieldname] == old_id)
                    .values(**{f.fieldname: new_id})
                )


async def _rename_multilink_refs(
    session: AsyncSession,
    doctype_name: str,
    old_id: str,
    new_id: str,
    *,
    is_merge: bool = False,
) -> None:
    """Update grunt_core_multi_link rows where *old_id* is either side of the link.

    On ``is_merge`` (*new_id* already exists) the parent side is left alone -
    the delete pipeline drops the source document's own multi-link rows - and
    the link side is de-duplicated: an incoming reference to *old_id* is
    removed rather than repointed when the same holder already references
    *new_id*.
    """
    ml = MULTI_LINK_TABLE

    if not is_merge:
        await session.execute(
            update(ml)
            .where(ml.c.parent_name == old_id, ml.c.parent_doctype == doctype_name)
            .values(parent_name=new_id)
        )
    else:
        # Drop incoming refs to old_id whose holder already references new_id,
        # so the repoint below can't create a semantic duplicate.
        twin = ml.alias("ml_twin")
        twin_exists = (
            select(1)
            .where(
                twin.c.parent_doctype == ml.c.parent_doctype,
                twin.c.parent_name == ml.c.parent_name,
                twin.c.parent_field == ml.c.parent_field,
                twin.c.link_doctype == ml.c.link_doctype,
                twin.c.link_name == new_id,
            )
            .correlate(ml)
            .exists()
        )
        await session.execute(
            ml.delete().where(
                ml.c.link_name == old_id,
                ml.c.link_doctype == doctype_name,
                twin_exists,
            )
        )

    await session.execute(
        update(ml)
        .where(ml.c.link_name == old_id, ml.c.link_doctype == doctype_name)
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
            sys_dt = await grunt.get_meta(sys_dt_name)
            if sys_dt is None:
                continue
            sys_table = sys_dt.table
            if sys_fieldname in sys_table.c:
                await session.execute(
                    sys_table.update()
                    .where(sys_table.c[sys_fieldname] == old_id)
                    .values(**{sys_fieldname: new_id})
                )
        except Exception as exc:
            log.warning(
                "document.rename_system_ref_failed",
                doctype=sys_dt_name,
                field=sys_fieldname,
                error=str(exc),
            )
            continue


async def repoint_references(
    session: AsyncSession,
    dt_meta: Meta,
    doctype_name: str,
    old_id: str,
    new_id: str,
    *,
    is_merge: bool = False,
) -> None:
    """Repoint every reference from *old_id* to *new_id* across all DocTypes.

    Shared by :func:`rename_document` (*old_id* disappears, *new_id* is a fresh
    id) and the replace-on-delete flow (``is_merge=True`` - *new_id* already
    exists, so duplicate multi-link rows are pruned instead of blindly moved).
    Covers Link fields (top-level and child-table), child ``parent_name``,
    MultiLink rows and the hardcoded system references.
    """
    await _rename_child_and_link_refs(session, dt_meta, doctype_name, old_id, new_id)
    await _rename_multilink_refs(session, doctype_name, old_id, new_id, is_merge=is_merge)
    await _rename_system_refs(session, old_id, new_id)


async def validate_replacement(
    session: AsyncSession,
    dt: Any,
    source_id: str,
    target_id: str,
) -> None:
    """Guard a replace-on-delete request before any rows are touched.

    Rejects a target that is the document itself, does not exist, or - for a
    tree DocType - is a descendant of the document being deleted (which would
    orphan the branch).
    """
    if source_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("The replacement cannot be the document being deleted"),
        )

    table = dt.table

    exists = await session.scalar(select(table.c.name).where(table.c.name == target_id))
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Replacement document “%(name)s” not found") % {"name": target_id},
        )

    parent_field = getattr(dt, "tree_parent_field", None)
    if parent_field and parent_field in table.c:
        cursor: str | None = target_id
        seen: set[str] = set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            cursor = await session.scalar(
                select(table.c[parent_field]).where(table.c.name == cursor)
            )
            if cursor == source_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_("A descendant cannot be used as the replacement"),
                )


async def rename_document(
    session: AsyncSession,
    engine: AsyncEngine,
    doctype_name: str,
    old_id: str,
    new_id: str,
    user: str,
) -> dict[str, Any]:
    """Update the primary ID of a document and cascade changes to all references."""

    async def _load(doc_id: str) -> dict[str, Any]:
        doc = await load_document(doctype_name, doc_id, session=session, engine=engine)
        return doc.as_dict()

    if old_id == new_id:
        return await _load(old_id)

    dt = await grunt.get_meta(doctype_name)
    if dt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype_name},
        )
    if not store_for(dt, session).can(REFERENCES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("Cannot rename virtual documents"),
        )

    table = dt.table

    exists_q = select(table.c.name).where(table.c.name == new_id)
    exists_res = await session.execute(exists_q)
    if exists_res.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_("Document with name '%(new_id)s' already exists") % {"new_id": new_id},
        )

    await session.execute(table.update().where(table.c.name == old_id).values(name=new_id))

    await repoint_references(session, dt, doctype_name, old_id, new_id)

    await session.flush()

    # Update search index: delete old, re-index under the new id.

    await search_index_service.remove_document(session, doctype_name, old_id)
    new_doc = await _load(new_id)
    await search_index_service.index_document(session, doctype_name, dt.doc, new_doc)

    log.info("document.renamed", doctype=doctype_name, old=old_id, new=new_id)
    return new_doc
