"""AssignmentLog DocType controller."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

import grunt
from grunt.app import grunt as grunt_app
from grunt.document.base import Document

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class AssignmentLog(Document):
    """AssignmentLog DocType controller."""

    @classmethod
    async def create(
        cls,
        *,
        rule_id: str | None,
        doctype_affected: str,
        document_id: str,
        assigned_to: str,
        assignment_method: str,
        status: str,
        error_message: str | None = None,
        filters_matched: bool = True,
        session: AsyncSession | None = None,
    ) -> None:
        """Зберегти запис про призначення в AssignmentLog.

        Args:
            rule_id: ID правила AssignmentRule (або None).
            doctype_affected: Назва DocType, для якого відбулось призначення.
            document_id: ID документа.
            assigned_to: Email або ID користувача.
            assignment_method: "user" або "role".
            status: "Success" або "Error".
            error_message: Опис помилки (якщо status == "Error").
            filters_matched: Чи збіглися фільтри правила.
            session: Async DB session.
        """
        if not session:
            return

        log_doc: dict[str, Any] = {
            "rule_id": rule_id,
            "doctype_affected": doctype_affected,
            "document_id": document_id,
            "assigned_to": assigned_to,
            "assignment_method": assignment_method,
            "status": status,
            "error_message": error_message,
            "filters_matched": filters_matched,
        }

        try:
            async with grunt_app.system_context(session):
                await grunt_app.bulk_insert("AssignmentLog", [log_doc])
        except Exception as exc:
            logger.exception("assignment.log_error", exc_info=exc)


# ------------------------------------------------------------------
# Whitelisted API
# ------------------------------------------------------------------


@grunt.whitelist()
async def list_logs(
    doctype: str | None = None,
    document_id: str | None = None,
    assigned_to: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List assignment logs with filters."""
    filters: dict[str, Any] = {}
    if doctype:
        filters["doctype_affected"] = doctype
    if document_id:
        filters["document_id"] = document_id
    if assigned_to:
        filters["assigned_to"] = assigned_to
    if status:
        filters["status"] = status

    logs = await grunt_app.get_list(
        "AssignmentLog",
        filters=filters,
        limit=int(limit),
        order_by="timestamp",
        order="desc",
    )
    total = await grunt_app.count("AssignmentLog", filters=filters)

    return {"data": logs, "count": total}
