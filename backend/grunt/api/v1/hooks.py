from typing import Any

from fastapi import APIRouter, Depends

from grunt.app import grunt
from grunt.core.auth.dependencies import superadmin_user
from grunt.core.hooks import DOC_EVENT_REGISTRY, HOOK_REGISTRY

router = APIRouter()


@router.get("/events")
async def list_events() -> list[str]:
    return list(HOOK_REGISTRY.keys())


@router.get("/")
async def get_hooks(
    _: Any = Depends(superadmin_user),
) -> dict[str, Any]:
    """Return all registered hooks (Global and DocType-specific)."""

    # 1. Collect Global Python Hooks
    hooks = []
    for event, list_hooks in HOOK_REGISTRY.items():
        for h in list_hooks:
            hooks.append(
                {
                    "source": "Python (Global)",
                    "event": event,
                    "handler": str(h["handler"]),
                    "priority": h["priority"],
                    "doctype": "*",
                }
            )

    # 2. Collect DocType Python Hooks
    for doctype, events in DOC_EVENT_REGISTRY.items():
        for event, list_hooks in events.items():
            for h in list_hooks:
                hooks.append(
                    {
                        "source": "Python (DocType)",
                        "event": event,
                        "handler": str(h["handler"]),
                        "priority": h["priority"],
                        "doctype": doctype,
                    }
                )

    # 3. Collect Server Scripts from Database
    try:
        scripts = await grunt.get_list(
            "ServerScript",
            filters={"disabled": False},
            fields=["event", "script_type", "api_method", "name", "reference_doctype"],
            limit=1000
        )

        for s in scripts:
            hooks.append(
                {
                    "source": "Database (Server Script)",
                    "event": s["event"]
                    if s["script_type"] == "DocType Event"
                    else s.get("api_method") or "Global",
                    "handler": s["name"],
                    "priority": 10,  # Scripts use standard priority
                    "doctype": s.get("reference_doctype")
                    if s["script_type"] == "DocType Event"
                    else "*",
                }
            )
    except Exception:
        pass  # ServerScript might not exist yet or error

    return {"success": True, "data": hooks}
