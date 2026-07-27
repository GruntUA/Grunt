from __future__ import annotations

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


async def log_activity(event: str, **kwargs) -> None:
    """Log document lifecycle events to ActivityLog."""
    doctype = kwargs.get("doctype")
    if not doctype or doctype in _SKIP_DOCTYPES:
        return

    action = _ACTION_MAP.get(event)
    doc = kwargs.get("doc") or kwargs.get("doc_id")
    user = kwargs.get("user")

    if not action or not doc or not user:
        return

    doc_id = doc.get("name") if isinstance(doc, dict) else str(doc)
    user_email = user.email if hasattr(user, "email") else str(user)

    details: dict | None = None
    if action == "Update":
        changed = [f for f in (kwargs.get("changed_fields") or []) if f not in _SKIP_FIELDS]
        if changed:
            details = {"changed_fields": changed}

    try:
        await grunt.new_doc(
            "ActivityLog",
            {
                "doctype": doctype,
                "doc_id": doc_id,
                "user": user_email,
                "action": action,
                "details": details,
            },
        )
    except Exception as e:
        logger.warning("activity.log_failed", error=str(e), doctype=doctype, doc_id=doc_id)
