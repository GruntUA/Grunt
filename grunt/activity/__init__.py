from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from grunt.app import grunt
from grunt.document.versioning import _SKIP_FIELDS

logger = structlog.get_logger()

# Doctypes that must NEVER be logged anywhere — high-frequency system churn
# (sessions, queued mail, webhook/profiler/scheduler traffic). Recording these
# is pure noise in every context, including per-document timelines.
_SKIP_DOCTYPES = frozenset(
    {
        "ActivityLog",
        "BackgroundTaskLog",
        "ErrorLog",
        "UserSession",
        "Notification",
        "PushSubscription",
        "EmailQueue",
        "ScheduledJobLog",
        "WebhookLog",
        "IncomingWebhookLog",
        "AssignmentLog",
        "SqlProfilerQuery",
        "SqlProfilerRequest",
        "SqlProfilerSpan",
    }
)

# Additional doctypes hidden from the GLOBAL activity feed only. These are
# config/metadata records whose changes are administrative, not day-to-day
# business activity — but they stay visible in a specific document's timeline.
FEED_HIDDEN_DOCTYPES = _SKIP_DOCTYPES | frozenset(
    {
        "DocType",
        "DocField",
        "DocTypePermission",
        "DocTypeStatusIndicator",
        "Role",
        "UserRole",
        "AppMenu",
        "WorkspaceSidebarItem",
        "Page",
        "PageWidget",
        "Dashboard",
        "DashboardWidget",
        "DashboardChart",
        "NumberCard",
        "Report",
        "PrintFormat",
        "WebForm",
        "ClientScript",
        "ServerScript",
        "Translation",
        "SystemSettings",
        "NamingSeries",
        "GruntInstalledApp",
        "DocVersion",
        "Bookmark",
        "DocTag",
        "DocLink",
    }
)


def is_feed_hidden(doctype: str | None) -> bool:
    """Whether a doctype should be excluded from the global activity feed."""
    return doctype in FEED_HIDDEN_DOCTYPES


_ACTION_MAP = {
    "after_insert": "Create",
    "after_update": "Update",
    "after_delete": "Delete",
}


async def record_activity(
    doctype: str,
    doc_id: str,
    action: str,
    *,
    user_email: str,
    details: dict | None = None,
    broadcast: bool = True,
) -> None:
    """Write one ActivityLog entry and (optionally) broadcast it live.

    The single write path for the activity feed. Must be called within an
    active grunt context (ambient session/user). Skips system churn centrally.

    Writes as SYSTEM_USER, not the ambient caller: `create` on ActivityLog
    is restricted to System Manager (write/delete always were, to keep the
    audit trail tamper-proof) precisely so a regular user can't forge an
    entry via the generic docs CRUD — attributing an action to someone else,
    or inventing one that never happened. This is the *only* legitimate
    write path, so it must work regardless of the acting user's own role.
    """
    if not doctype or doctype in _SKIP_DOCTYPES:
        return
    try:
        async with grunt.system_context(grunt._require_session()):
            doc = await grunt.new_doc(
                "ActivityLog",
                {
                    "doctype": doctype,
                    "doc_id": str(doc_id),
                    "user": user_email,
                    "action": action,
                    "details": details,
                },
            )
    except Exception as e:
        logger.warning("activity.log_failed", error=str(e), doctype=doctype, doc_id=doc_id)
        return

    if broadcast:
        await _broadcast_activity(doc, doctype, str(doc_id), action, user_email)


async def _broadcast_activity(
    doc: dict[str, Any], doctype: str, doc_id: str, action: str, user_email: str
) -> None:
    """Push a live activity event to the global site WebSocket channel."""
    try:
        from grunt.api.v1.ws import manager

        created_at = doc.get("created_at")
        # "site" is the authenticated site-wide channel. Never "public:site" —
        # that endpoint takes no token, which would stream user emails and
        # document ids to anyone who knows the URL.
        await manager.broadcast(
            "site",
            "activity",
            {
                "name": doc.get("name"),
                "doctype": doctype,
                "doc_id": doc_id,
                "action": action,
                "user": user_email,
                "created_at": created_at.isoformat()
                if isinstance(created_at, datetime)
                else str(created_at or ""),
            },
        )
    except Exception:
        logger.debug("activity.broadcast_failed", doctype=doctype, doc_id=doc_id)


async def log_activity(event: str, **kwargs) -> None:
    """Hook adapter: map a lifecycle event to an ActivityLog entry."""
    action = _ACTION_MAP.get(event)
    doc = kwargs.get("doc") or kwargs.get("doc_id")
    user = kwargs.get("user")
    doctype = kwargs.get("doctype")

    if not action or not doc or not user or not doctype:
        return

    doc_id = str(doc.get("name") or "") if isinstance(doc, dict) else str(doc)
    if not doc_id:
        return
    user_email = user.email if hasattr(user, "email") else str(user)

    details: dict | None = None
    if action == "Update":
        changed = [f for f in (kwargs.get("changed_fields") or []) if f not in _SKIP_FIELDS]
        if changed:
            details = {"changed_fields": changed}

    await record_activity(doctype, doc_id, action, user_email=user_email, details=details)
