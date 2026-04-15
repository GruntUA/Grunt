"""Hooks API whitelisted methods."""

from __future__ import annotations
from typing import Any
import grunt

@grunt.whitelist()
async def list_events() -> list[str]:
    """Return all whitelisted event types."""
    from grunt.core.hooks import HOOK_REGISTRY
    return list(HOOK_REGISTRY.keys())

@grunt.whitelist()
async def get_hooks() -> list[dict[str, Any]]:
    """Return all registered hooks (Global, DocType, and Database). Admin only."""
    from grunt.app import grunt as grunt_app
    from grunt.core.hooks import DOC_EVENT_REGISTRY, HOOK_REGISTRY

    user = grunt_app._require_user()
    if not user.is_superadmin:
        grunt.throw("Admin only", "PERMISSION_DENIED")

    hooks = []
    
    # 1. Collect Global Python Hooks
    for event, list_hooks in HOOK_REGISTRY.items():
        for h in list_hooks:
            hooks.append({
                "source": "Python (Global)",
                "event": event,
                "handler": str(h["handler"]),
                "priority": h["priority"],
                "doctype": "*",
            })

    # 2. Collect DocType Python Hooks
    for doctype, events in DOC_EVENT_REGISTRY.items():
        for event, list_hooks in events.items():
            for h in list_hooks:
                hooks.append({
                    "source": "Python (DocType)",
                    "event": event,
                    "handler": str(h["handler"]),
                    "priority": h["priority"],
                    "doctype": doctype,
                })

    # 3. Collect Server Scripts from Database
    try:
        scripts = await grunt.get_list(
            "ServerScript",
            filters={"disabled": False},
            fields=["event", "script_type", "api_method", "name", "reference_doctype"],
            limit=1000
        )
        for s in scripts:
            hooks.append({
                "source": "Database (Server Script)",
                "event": s["event"] if s["script_type"] == "DocType Event" else s.get("api_method") or "Global",
                "handler": s["name"],
                "priority": 10,
                "doctype": s.get("reference_doctype") if s["script_type"] == "DocType Event" else "*",
            })
    except Exception:
        pass

    return hooks
