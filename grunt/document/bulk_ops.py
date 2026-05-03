"""Bulk document operations shared by API handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TYPE_CHECKING

from grunt.app import grunt as grunt_app

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.User import User


ProgressCallback = Callable[[int, int, int], Awaitable[None]]


class BulkDeleteTask:
    """Background task that deletes many documents and streams progress."""

    def __init__(self) -> None:
        from grunt.api.v1.ws import manager  # noqa: PLC0415

        self._manager = manager

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
        from grunt.db.session import async_session_factory  # noqa: PLC0415

        total = len(ids)
        progress_cb = self._make_progress_cb(user_email, total)

        try:
            async with async_session_factory() as session:
                async with grunt_app.context(session, engine, user):
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
            import structlog
            structlog.get_logger().exception("bulk_delete.failed", doctype=doctype, error=str(e))
            await self._manager.send_to_user(
                user_email,
                {
                    "event": "bulk_delete_done",
                    "data": {"deleted": 0, "total": total, "errors": [str(e)]},
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
