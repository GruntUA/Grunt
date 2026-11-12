"""``NotificationDelivery`` rows - one per (notification × recipient × channel).

Kept apart from the channels and the dispatcher (:mod:`grunt.notification.delivery`):
the email queue and the push sender update the outcome of a delivery they
carried out, and must not import the channels that import them.
"""

import secrets
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.local import require_session, system_context
from grunt.log import log

_db = GruntDB()  # stateless: reads through the context's session

DOCTYPE = "NotificationDelivery"

Status = Literal["Queued", "Sent", "Skipped", "Error"]


def new_id() -> str:
    """A delivery's name, known before its row exists (a channel may pass it on)."""
    return f"nd-{secrets.token_urlsafe(9)}"


async def record(row: dict[str, Any], *, session: AsyncSession | None = None) -> None:
    """Insert one delivery row (raw insert: a log, no hooks)."""
    now = datetime.now(UTC)
    async with system_context(session or require_session()):
        await _db.insert_one(
            DOCTYPE,
            {
                "owner": "system",
                "created_at": now,
                "modified_at": now,
                "modified_by": "system",
                **row,
                "reason": (row.get("reason") or None) and str(row["reason"])[:1000],
                "subject": (row.get("subject") or "")[:500],
            },
        )


async def settle(
    filters: dict[str, Any],
    status: Status,
    *,
    reason: str | None = None,
    **links: str | None,
) -> int:
    """Set the outcome of the deliveries matching *filters* - best-effort.

    ``settle({"email_queue": qid}, "Sent", email_message=mid)`` - the email
    queue after sending; ``settle({"name": did}, "Skipped", reason=...)`` - the
    push sender.
    """
    values: dict[str, Any] = {
        "status": status,
        "reason": reason[:1000] if reason else None,
        "modified_at": datetime.now(UTC),
        **{k: v for k, v in links.items() if v},
    }
    try:
        async with system_context(require_session()):
            return await _db.bulk_update(DOCTYPE, filters, values)
    except Exception:
        log.exception("notification.delivery_settle_failed", filters=filters)
        return 0
