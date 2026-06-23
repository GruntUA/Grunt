from __future__ import annotations

import structlog

from grunt.app import grunt
from grunt.document.versioning import _SKIP_FIELDS

logger = structlog.get_logger()

_SKIP_DOCTYPES = frozenset({"ActivityLog", "BackgroundTaskLog", "ErrorLog"})

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
