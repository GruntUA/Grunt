"""Helpers for document update side effects.

Extracted from ``DocumentWriteMixin`` to keep write pipeline orchestration thin
while preserving existing behavior.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.doctypes.user.user import User

ProgressCallback = Callable[[int], Awaitable[None]]

logger = structlog.get_logger()


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
    from grunt.core.document.versioning import version_service  # noqa: PLC0415

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
            logger.exception("version.create_error", doctype=doctype_name, doc_id=real_id)

    if diff_changes:
        try:
            from grunt.app import grunt as _g  # noqa: PLC0415

            async with _g.context(session=session, engine=engine, user=user):
                await _g.new_doc(
                    "ActivityLog",
                    {
                        "doctype": doctype_name,
                        "doc_id": real_id,
                        "action": "Update",
                        "user": user.email,
                        "details": {"changes": diff_changes},
                    },
                )
        except Exception:  # noqa: BLE001
            logger.warning("activity_log.update_failed", doctype=doctype_name, doc_id=real_id)


async def fire_update_services(
    *,
    session: AsyncSession,
    doctype_name: str,
    dt: Any,
    result: dict[str, Any],
) -> None:
    """Update search index and fire outgoing webhooks after successful update."""
    from grunt.core.search.service import search_index_service  # noqa: PLC0415
    from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

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
    from grunt.core.search.service import search_index_service  # noqa: PLC0415
    from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

    await search_index_service.remove_document(session, doctype_name, real_id)
    await webhook_service.fire(session, "after_delete", doctype_name, existing)


async def fire_bulk_delete_webhooks(
    *,
    session: AsyncSession,
    doctype_name: str,
    docs: list[dict[str, Any]],
) -> None:
    """Fire outgoing after_delete webhooks for each deleted document."""
    from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

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
    from grunt.app import GruntError  # noqa: PLC0415
    from grunt.core.document.registry import document_registry  # noqa: PLC0415

    controllers: list[tuple[dict[str, Any], Any]] = []
    for i, doc in enumerate(docs):
        controller_cls = document_registry.get(doctype_name)
        ctrl = controller_cls(doctype_name, doc, user, session)
        try:
            await ctrl.before_delete()
        except GruntError as e:
            errors.append(f"{doc['id']}: {e}")
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
    from grunt.app import GruntError  # noqa: PLC0415

    docs_for_webhook: list[dict[str, Any]] = []
    for doc, ctrl in controllers:
        real_id = str(doc["id"])
        try:
            await ctrl.after_delete()
        except GruntError as e:
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
    """Execute batched DELETE + MultiLink cleanup + search index cleanup."""
    from grunt.core.search.service import search_index_service  # noqa: PLC0415

    await session.execute(table.delete().where(table.c.id.in_(final_ids)))
    await ml.delete_all_for_docs(doctype_name, final_ids)
    await session.flush()
    await search_index_service.remove_documents(session, doctype_name, final_ids)


async def bulk_delete_virtual(
    *,
    doctype_name: str,
    ids: list[str],
    user: User,
) -> tuple[int, list[str]]:
    """Delete virtual documents one-by-one and aggregate errors."""
    from grunt.core.document.virtual import _virtual_delete  # noqa: PLC0415

    deleted = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            await _virtual_delete(doctype_name, user, doc_id)
            deleted += 1
        except Exception as e:  # noqa: BLE001
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
    await session.execute(table.delete().where(table.c.id == real_id))
    await ml.delete_all_for_doc(doctype_name, real_id)
    await session.flush()


async def collect_bulk_delete_candidates(
    *,
    session: AsyncSession,
    dt: Any,
    table: Any,
    ids: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch and validate candidate docs for bulk delete."""
    from sqlalchemy import select as sa_select  # noqa: PLC0415

    existing_rows: dict[str, dict[str, Any]] = {}
    result = await session.execute(sa_select(table).where(table.c.id.in_(ids)))
    for row in result.fetchall():
        existing_rows[str(row._mapping["id"])] = dict(row._mapping)

    errors: list[str] = []
    to_delete: list[dict[str, Any]] = []

    for doc_id in ids:
        doc = existing_rows.get(doc_id)
        if doc is None:
            errors.append(f"{doc_id}: not found")
            continue
        if dt.is_submittable and doc.get("docstatus") == 1:
            errors.append(f"{doc_id}: submitted — cancel before delete")
            continue
        to_delete.append(doc)

    return to_delete, errors
