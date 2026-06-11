"""Bulk document operations shared by API handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, cast

import structlog

from grunt.app import grunt as grunt_app

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


ProgressCallback = Callable[[int, int, int], Awaitable[None]]

logger = structlog.get_logger()

# Records per loop iteration when deleting all matching docs.
# Small enough to avoid huge IN() queries; large enough to be efficient.
_DELETE_ALL_BATCH = 5_000


class BulkDeleteTask:
    """Background task that deletes many documents and streams progress."""

    def __init__(self) -> None:
        from grunt.api.v1.ws import manager

        self._manager = manager

    # ── Delete explicit list of IDs ───────────────────────────────────────

    async def run(
        self,
        doctype: str,
        ids: Sequence[str],
        *,
        user: User,
        user_email: str,
        engine: Any,
    ) -> None:
        """Delete document IDs and send progress/done events to one user."""
        from grunt.db.session import async_session_factory

        total = len(ids)
        progress_cb = self._make_progress_cb(user_email, total)

        try:
            async with async_session_factory() as session, grunt_app.context(session, engine, user):
                deleted, errors = await grunt_app.bulk_delete_docs(
                    doctype,
                    list(ids),
                    progress_cb=progress_cb,
                )

            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {"deleted": deleted, "total": total, "errors": errors},
                },
            )
        except Exception as e:
            logger.exception("bulk_delete.failed", doctype=doctype, error=str(e))
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {"deleted": 0, "total": total, "errors": [str(e)]},
                },
            )

    # ── Delete all matching filters in a loop ─────────────────────────────

    async def run_delete_all(
        self,
        doctype: str,
        *,
        filters: dict[str, str] | None,
        search: str | None,
        user: User,
        user_email: str,
        engine: Any,
        batch_size: int = _DELETE_ALL_BATCH,
    ) -> None:
        """Delete ALL documents matching *filters* in rolling batches.

        Unlike ``run()``, this method does not pre-fetch all IDs.
        Each iteration fetches the next ``batch_size`` surviving records and
        deletes them, until no records remain.  Progress is streamed via
        WebSocket after every batch.
        """
        from grunt.db.session import async_session_factory

        total_deleted = 0
        all_errors: list[str] = []

        # One-time count for accurate progress display.
        try:
            async with async_session_factory() as session, grunt_app.context(session, engine, user):
                grand_total: int = await grunt_app.count(doctype, filters=filters)  # type: ignore[arg-type]
        except Exception:
            grand_total = 0

        logger.info(
            "bulk_delete_all.started",
            doctype=doctype,
            grand_total=grand_total,
            batch_size=batch_size,
        )

        try:
            while True:
                # Fetch the next batch of IDs that still exist.
                async with (
                    async_session_factory() as session,
                    grunt_app.context(session, engine, user),
                ):
                    rows = await grunt_app.get_list(
                        doctype,
                        filters=filters,
                        search=search,
                        fields=["name"],
                        limit=batch_size,
                        page=1,
                    )

                if not rows:
                    break  # nothing left

                ids = [str(r["name"]) for r in rows]

                # Delete the batch.
                async with (
                    async_session_factory() as session,
                    grunt_app.context(session, engine, user),
                ):
                    deleted, errors = await grunt_app.bulk_delete_docs(doctype, ids)

                total_deleted += deleted
                all_errors.extend(errors)

                # Stream progress to the requesting user.
                await self._manager.send_to_user(
                    user_email,
                    {
                        "event": "bulk_delete_progress",
                        "data": {
                            "done": total_deleted,
                            "total": grand_total,
                            "errors": len(all_errors),
                        },
                    },
                )

                logger.info(
                    "bulk_delete_all.batch",
                    doctype=doctype,
                    batch=len(ids),
                    total_deleted=total_deleted,
                    grand_total=grand_total,
                )

                if deleted == 0:
                    # No progress made — all docs in this batch failed (e.g. blocked
                    # by a before_delete hook).  Stop to avoid an infinite loop.
                    logger.warning(
                        "bulk_delete_all.no_progress",
                        doctype=doctype,
                        batch_errors=len(errors),
                    )
                    break

                if len(rows) < batch_size:
                    # Last batch was smaller than requested → we're done.
                    break

            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {
                        "deleted": total_deleted,
                        "total": grand_total,
                        "errors": all_errors,
                    },
                },
            )
            logger.info(
                "bulk_delete_all.done",
                doctype=doctype,
                total_deleted=total_deleted,
                errors=len(all_errors),
            )

        except Exception as e:
            logger.exception("bulk_delete_all.failed", doctype=doctype, error=str(e))
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {
                        "deleted": total_deleted,
                        "total": grand_total,
                        "errors": all_errors + [str(e)],
                    },
                },
            )

    # ── Fast truncate (superadmin only, no hooks) ─────────────────────────

    async def run_fast_delete_all(
        self,
        doctype: str,
        *,
        filters: dict[str, str] | None,
        user: User,
        user_email: str,
        engine: Any,
    ) -> None:
        """Delete records directly via SQL — no lifecycle hooks, no per-row overhead.

        ~100× faster than ``run_delete_all()`` for large datasets.
        Only superadmins may call this method.

        Steps:
        1. DELETE FROM <doctype table> [WHERE <filters>]
        2. DELETE FROM grunt_multi_links WHERE parent_doctype = doctype
        3. DELETE FROM grunt_search_index WHERE doctype = doctype
        4. Write one summary ActivityLog entry
        """
        import uuid
        from datetime import UTC, datetime

        from sqlalchemy import delete as sa_delete
        from sqlalchemy.engine import CursorResult

        from grunt.db.session import async_session_factory
        from grunt.document.query import _apply_filters
        from grunt.metadata.compiler import (
            MULTI_LINK_TABLE,
            compile_doctype_to_table,
        )
        from grunt.metadata.registry import doctype_registry
        from grunt.search.service import _search_index_table

        if not user.is_superadmin:
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {
                        "deleted": 0,
                        "total": 0,
                        "errors": ["Тільки суперадмін може виконати швидке видалення"],
                    },
                },
            )
            return

        try:
            async with async_session_factory() as session, grunt_app.context(session, engine, user):
                dt = await doctype_registry.get(doctype)
                table = compile_doctype_to_table(dt)

                # ── 1. Delete main rows ──────────────────────────────────
                del_stmt = sa_delete(table)
                if filters:
                    del_stmt = _apply_filters(del_stmt, table, filters)
                result = cast("CursorResult", await session.execute(del_stmt))
                deleted: int = result.rowcount or 0

                # ── 2. Delete MultiLinks ─────────────────────────────────
                await session.execute(
                    sa_delete(MULTI_LINK_TABLE).where(MULTI_LINK_TABLE.c.parent_doctype == doctype)
                )

                # ── 3. Delete search index ───────────────────────────────
                await session.execute(
                    sa_delete(_search_index_table).where(_search_index_table.c.doctype == doctype)
                )

                # ── 4. Summary ActivityLog entry ─────────────────────────
                try:
                    dt_log = await doctype_registry.get("ActivityLog")
                    t_log = compile_doctype_to_table(dt_log)
                    now = datetime.now(UTC)
                    table_cols = {c.name for c in t_log.c}
                    log_row: dict[str, Any] = {
                        "name": uuid.uuid4().hex[:10],
                        "doctype": doctype,
                        "doc_id": "fast-bulk-delete",
                        "user": user_email,
                        "action": "Delete",
                        "details": {"count": deleted, "fast": True},
                        "owner": user_email,
                        "created_at": now,
                        "modified_at": now,
                        "modified_by": user_email,
                        "docstatus": 0,
                    }
                    await session.execute(
                        t_log.insert().values(
                            **{k: v for k, v in log_row.items() if k in table_cols}
                        )
                    )
                except Exception:
                    logger.warning("fast_delete.activity_log_failed", doctype=doctype)

                await session.flush()

            logger.info("fast_delete.done", doctype=doctype, deleted=deleted, user=user_email)
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {"deleted": deleted, "total": deleted, "errors": []},
                },
            )

        except Exception as e:
            logger.exception("fast_delete.failed", doctype=doctype, error=str(e))
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {"deleted": 0, "total": 0, "errors": [str(e)]},
                },
            )

    def _make_progress_cb(self, user_email: str, total: int) -> ProgressCallback:
        async def _progress(done: int, _total: int, error_count: int) -> None:
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_progress",
                    "data": {"done": done, "total": total, "errors": error_count},
                },
            )

        return _progress
