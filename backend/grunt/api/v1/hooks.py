from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from grunt.core.db.session import get_session
from grunt.core.auth.dependencies import superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.hooks import HOOK_REGISTRY, DOC_EVENT_REGISTRY
from typing import Any

router = APIRouter()

@router.get("/")
async def get_hooks(
    user: GruntUser = Depends(superadmin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all registered hooks (Global and DocType-specific)."""
    
    # 1. Collect Global Python Hooks
    hooks = []
    for event, list_hooks in HOOK_REGISTRY.items():
        for h in list_hooks:
            hooks.append({
                "source": "Python (Global)",
                "event": event,
                "handler": str(h["handler"]),
                "priority": h["priority"],
                "doctype": "*"
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
                    "doctype": doctype
                })
                
    # 3. Collect Server Scripts from Database
    from grunt.core.metadata.registry import doctype_registry # noqa
    from grunt.core.metadata.compiler import compile_doctype_to_table # noqa
    from sqlalchemy import select # noqa
    
    try:
        ss_dt = doctype_registry.get_sync("ServerScript") # Use get_sync if async not easier here
        table = compile_doctype_to_table(ss_dt)
        q = select(table).where(table.c.disabled == False)
        result = await session.execute(q)
        scripts = result.mappings().all()
        
        for s in scripts:
            hooks.append({
                "source": "Database (Server Script)",
                "event": s["event"] if s["script_type"] == "DocType Event" else s["api_method"] or "Global",
                "handler": s["name"],
                "priority": 10, # Scripts use standard priority
                "doctype": s["reference_doctype"] if s["script_type"] == "DocType Event" else "*"
            })
    except Exception:
        pass # ServerScript might not exist yet or error
        
    return {"success": True, "data": hooks}
