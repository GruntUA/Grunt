from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

async def log_activity(event: str, **kwargs) -> None:
    """Log document lifecycle events to ActivityLog."""
    doctype = kwargs.get("doctype")
    doc = kwargs.get("doc") or kwargs.get("doc_id")
    user = kwargs.get("user")
    session = kwargs.get("session")

    # Prevent infinite loops if ActivityLog triggers hooks
    if doctype == "ActivityLog":
        return

    action_map = {
        "after_insert": "Create",
        "after_update": "Update",
        "after_delete": "Delete"
    }

    action = action_map.get(event)
    if not action or not doctype or not doc or not user or not session:
        return

    doc_id = doc.get("id") if isinstance(doc, dict) else str(doc)
    user_email = user.email if hasattr(user, "email") else str(user)
    
    # If it's the system user pulling emails or running bg tasks, we can log it too.
    
    try:
        from grunt.core.metadata.registry import doctype_registry
        from grunt.core.metadata.compiler import compile_doctype_to_table

        dt = await doctype_registry.get("ActivityLog")
        table = compile_doctype_to_table(dt)

        # Basic ID and standard fields
        new_id = str(uuid.uuid4())
        name = new_id.split("-")[0]
        now = datetime.now(timezone.utc)

        row = {
            "id": new_id,
            "name": name,
            "owner": user_email,
            "created_at": now,
            "modified_at": now,
            "modified_by": user_email,
            "docstatus": 0,
            
            # Custom fields
            "reference_doctype": doctype,
            "reference_id": doc_id,
            "user": user_email,
            "action": action,
            "details": f"Document {action.lower()}d via {event}"
        }
        
        # Raw insert using the current transaction to avoid nested flushes triggering infinite events
        await session.execute(table.insert().values(**row))
        
    except Exception as e:
        logger.warning("activity.log_failed", error=str(e), doctype=doctype, doc_id=doc_id)
