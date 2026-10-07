"""Helpers for document update side effects.

Extracted from ``DocumentWriteMixin`` to keep write pipeline orchestration thin
while preserving existing behavior.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from itertools import islice
from typing import TYPE_CHECKING, Any

import grunt
from grunt import _, log
from grunt.document.registry import document_registry
from grunt.document.serde import audit_fields
from grunt.document.versioning import version_service
from grunt.errors import ApplicationError
from grunt.search.service import search_index_service
from grunt.webhook.service import webhook_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User

ProgressCallback = Callable[[int], Awaitable[None]]

# SQLite allows at most 999 host parameters per statement (SQLITE_LIMIT_VARIABLE_NUMBER).
# We use 900 as a safe upper bound; PostgreSQL supports far more.
_IN_CHUNK = 900


async def record_update_changes(
    *,
    session: AsyncSession,
    engine: AsyncEngine,
    doctype_name: str,
    real_id: str,
    dt: Any,
    existing: dict[str, Any],
    result: dict[str, Any],
    user: User,
) -> None:
    """Create a version record and write an ActivityLog diff (best-effort)."""
    diff_changes = version_service._compute_diff(existing, result)

    if dt.track_changes and diff_changes:
        try:
            await version_service.create_version(
                session=session,
                doctype=doctype_name,
                doc_id=real_id,
                old_doc=existing,
                new_doc=result,
                user=user.email,
            )
        except Exception:
            log.exception("version.create_error", doctype=doctype_name, doc_id=real_id)

    if diff_changes:
        from grunt.document.versioning import _SKIP_FIELDS

        changed_fields = [
            item["field"] for item in diff_changes if item["field"] not in _SKIP_FIELDS
        ]
        try:
            import grunt
            from grunt.activity import record_activity

            async with grunt.context(session=session, engine=engine, user=user):
                await record_activity(
                    doctype_name,
                    real_id,
                    "Update",
                    user_email=user.email,
                    details={"changed_fields": changed_fields} if changed_fields else None,
                )
        except Exception:
            log.warning("activity_log.update_failed", doctype=doctype_name, doc_id=real_id)

        try:
            from grunt.activity.follow import notify_followers_of_update

            await notify_followers_of_update(
                session=session,
                doctype=doctype_name,
                doc_id=real_id,
                dt=dt,
                changed_fields=changed_fields,
                actor_email=user.email,
            )
        except Exception:
            log.exception("follow.update_notify_failed", doctype=doctype_name, doc_id=real_id)


async def fire_update_services(
    *,
    session: AsyncSession,
    doctype_name: str,
    dt: Any,
    result: dict[str, Any],
) -> None:
    """Update search index and fire outgoing webhooks after successful update."""
    await search_index_service.index_document(session, doctype_name, dt, result)
    await webhook_service.fire(session, "after_update", doctype_name, result)


async def fire_delete_services(
    *,
    session: AsyncSession,
    doctype_name: str,
    real_id: str,
    existing: dict[str, Any],
) -> None:
    """Update external services after delete: search index and outgoing webhooks."""
    await search_index_service.remove_document(session, doctype_name, real_id)
    await webhook_service.fire(session, "after_delete", doctype_name, existing)


async def fire_bulk_delete_webhooks(
    *,
    session: AsyncSession,
    doctype_name: str,
    docs: list[dict[str, Any]],
) -> None:
    """Fire outgoing after_delete webhooks for each deleted document."""
    for doc in docs:
        await webhook_service.fire(session, "after_delete", doctype_name, doc)


async def run_bulk_before_delete_hooks(
    *,
    doctype_name: str,
    docs: list[dict[str, Any]],
    user: User,
    session: AsyncSession,
    errors: list[str],
    report: ProgressCallback | None = None,
) -> list[tuple[dict[str, Any], Any]]:
    """Run per-document before_delete hooks and keep only successful controllers."""
    controllers: list[tuple[dict[str, Any], Any]] = []
    for i, doc in enumerate(docs):
        controller_cls = document_registry.get(doctype_name)
        ctrl = controller_cls(doctype_name, doc, user, session)
        try:
            await ctrl.before_delete()
        except ApplicationError as e:
            errors.append(f"{doc['name']}: {e}")
            continue
        controllers.append((doc, ctrl))
        if report is not None:
            await report(i + 1)
    return controllers


async def run_bulk_after_delete_hooks(
    *,
    session: AsyncSession,
    doctype_name: str,
    controllers: list[tuple[dict[str, Any], Any]],
    errors: list[str],
) -> None:
    """Run per-document after_delete hooks and fire outgoing webhooks."""
    docs_for_webhook: list[dict[str, Any]] = []
    for doc, ctrl in controllers:
        real_id = str(doc["name"])
        try:
            await ctrl.after_delete()
        except ApplicationError as e:
            errors.append(f"{real_id}: {e}")
        docs_for_webhook.append(doc)

    await fire_bulk_delete_webhooks(
        session=session,
        doctype_name=doctype_name,
        docs=docs_for_webhook,
    )


async def run_bulk_delete_writes(
    *,
    session: AsyncSession,
    ml: Any,
    table: Any,
    doctype_name: str,
    final_ids: list[str],
) -> None:
    """Execute batched DELETE + MultiLink cleanup + search index cleanup.

    All IN-clause queries are chunked to stay within SQLite's 999-parameter limit.
    MultiLink and search-index helpers have their own internal chunking.
    """
    it = iter(final_ids)
    while chunk := list(islice(it, _IN_CHUNK)):
        await session.execute(table.delete().where(table.c.name.in_(chunk)))

    await ml.delete_all_for_docs(doctype_name, final_ids)
    await session.flush()
    await search_index_service.remove_documents(session, doctype_name, final_ids)


async def bulk_delete_one_by_one(
    session: AsyncSession,
    engine: Any,
    doctype_name: str,
    ids: list[str],
    user: User,
) -> tuple[int, list[str]]:
    """Delete documents one at a time through the delete pipeline - for a
    controller without a table to batch the DELETE on. Aggregates errors."""
    from grunt.document.base import new_document

    deleted = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            doc = await new_document(
                doctype_name, {"name": doc_id}, user=user, session=session, engine=engine
            )
            await doc.delete()
            deleted += 1
        except Exception as e:
            errors.append(f"{doc_id}: {e}")
    return deleted, errors


async def delete_row_and_links(
    *,
    session: AsyncSession,
    ml: Any,
    table: Any,
    doctype_name: str,
    real_id: str,
) -> None:
    """Delete main row and MultiLink relations, then flush pending writes."""
    await session.execute(table.delete().where(table.c.name == real_id))
    await ml.delete_all_for_doc(doctype_name, real_id)
    await session.flush()


async def collect_bulk_delete_candidates(
    *,
    session: AsyncSession,
    dt: Any,
    table: Any,
    ids: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch and validate candidate docs for bulk delete.

    The SELECT is chunked to stay within SQLite's 999-parameter limit.
    """
    from sqlalchemy import select as sa_select

    existing_rows: dict[str, dict[str, Any]] = {}
    it = iter(ids)
    while chunk := list(islice(it, _IN_CHUNK)):
        result = await session.execute(sa_select(table).where(table.c.name.in_(chunk)))
        for row in result.fetchall():
            existing_rows[str(row._mapping["name"])] = dict(row._mapping)

    errors: list[str] = []
    to_delete: list[dict[str, Any]] = []

    for doc_id in ids:
        doc = existing_rows.get(doc_id)
        if doc is None:
            errors.append(f"{doc_id}: not found")
            continue
        to_delete.append(doc)

    return to_delete, errors


async def write_bulk_delete_activity_log(
    *,
    session: AsyncSession,
    doctype_name: str,
    doc_ids: list[str],
    user_email: str,
    now: datetime | None = None,
) -> None:
    """Batch-insert ActivityLog rows for bulk deletion in a single SQL statement.

    This is a fast alternative to firing the ``after_delete`` hook N times.
    Each deleted document still gets its own audit row, so the trail is complete.
    """
    if not doc_ids:
        return

    _now = now or datetime.now(UTC)

    try:
        dt_log = await grunt.get_meta("ActivityLog")
        if dt_log is None:
            raise ValueError(_("DocType “%(doctype)s” not found") % {"doctype": "ActivityLog"})
        t_log = dt_log.table

        table_cols = {c.name for c in t_log.c}

        def _make_row(doc_id: str) -> dict:
            raw = {
                "name": uuid.uuid4().hex[:10],
                "ref_doctype": doctype_name,
                "doc_id": doc_id,
                "user": user_email,
                "action": "Delete",
                "details": None,
                **audit_fields(user_email, _now),
            }
            return {k: v for k, v in raw.items() if k in table_cols}

        # Chunk INSERT to stay within SQLite's per-statement parameter limit.
        # Each ActivityLog row has ~10 columns; 900 // 10 = 90 rows per INSERT.
        insert_chunk = max(1, _IN_CHUNK // 10)
        it = iter(doc_ids)
        while chunk := list(islice(it, insert_chunk)):
            await session.execute(t_log.insert(), [_make_row(doc_id) for doc_id in chunk])

        await session.flush()
        log.info(
            "bulk_delete.activity_log_written",
            doctype=doctype_name,
            count=len(doc_ids),
        )
    except Exception:
        log.warning(
            "bulk_delete.activity_log_failed",
            doctype=doctype_name,
            count=len(doc_ids),
        )
