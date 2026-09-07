"""ToDo controller — assignment notification.

A ToDo row *is* an assignment: someone (``assigned_to``) is put on the hook for
a document (``reference_doctype`` / ``reference_id``), optionally with a task
note in ``description``. On creation we ping that person.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

# A ToDo created without a real task note carries this placeholder as its
# description (see the frontend ``docsApi.assign``). Treat it as "no note".
_PLACEHOLDER_PREFIX = "Assigned to "


async def notify_assignee(**kwargs: Any) -> None:
    """``after_insert`` hook: tell ``assigned_to`` they have a new assignment."""
    doc: dict[str, Any] = kwargs.get("doc") or {}
    session = kwargs.get("session")
    if session is None:
        return

    assignee = (doc.get("assigned_to") or "").strip()
    if not assignee:
        return

    actor = kwargs.get("user")
    actor_email = getattr(actor, "email", "") or ""
    if assignee == actor_email:
        return  # assigned to yourself — no ping

    ref_dt = (doc.get("reference_doctype") or "").strip()
    ref_id = str(doc.get("reference_id") or "").strip()
    target = f"{ref_dt} {ref_id}".strip() or "документ"

    note = (doc.get("description") or "").strip()
    if note == f"{_PLACEHOLDER_PREFIX}{assignee}":
        note = ""

    subject = f"Вам призначено: {target}"
    message = note or f"Вас призначено відповідальним за {target}."

    from grunt.notification.service import notification_service

    try:
        await notification_service.notify(
            session,
            user=assignee,
            doctype=ref_dt or "ToDo",
            doc_id=ref_id or str(doc.get("name") or ""),
            subject=subject,
            message=message,
            email=True,
        )
    except Exception:
        logger.exception("todo.notify_assignee_failed", assignee=assignee)
