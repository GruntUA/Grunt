"""Workspace API — CRUD and counts for workspace navigation."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException, Query

from grunt.api.router import GruntRouter
from grunt.app import grunt
from grunt.core.document.registry import document_registry

logger = structlog.get_logger()

router = GruntRouter(prefix="", tags=["workspace"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _workspace_to_dict(ws: Any) -> dict[str, Any]:
    """Convert WorkspaceSidebar document to dict, filtering items by role."""
    items = []
    user = grunt.session
    for item in sorted(ws.get("sidebar_items") or [], key=lambda i: i.get("idx", 0)):
        # Role check for items
        item_roles = item.get("roles", "")
        if not user.is_superadmin and item_roles:
            allowed = {r.strip() for r in item_roles.split(",") if r.strip()}
            if not (allowed & set(user.roles)):
                continue

        item_type = item.get("type", "DocType")
        link_to = item.get("link_to", "")

        is_singleton = False
        if item_type == "DocType" and link_to:
            try:
                from grunt.core.metadata.registry import doctype_registry

                if link_to in doctype_registry._doctypes:
                    is_singleton = doctype_registry._doctypes[link_to].is_singleton
            except Exception:
                pass

        items.append(
            {
                "section": item.get("section", ""),
                "type": item_type,
                "label": item.get("label", ""),
                "icon": item.get("icon", ""),
                "link_to": link_to,
                "show_count": item.get("show_count", False),
                "count_filters": item.get("count_filters", ""),
                "show_new_btn": item.get("show_new_btn", False),
                "roles": item_roles,
                "sequence": item.get("idx", 0),
                "is_singleton": is_singleton,
            }
        )

    return {
        "name": ws.get("name"),
        "label": ws.get("label"),
        "app": ws.get("app", ""),
        "icon": ws.get("icon", "📁"),
        "color": ws.get("color", "#2D6A4F"),
        "description": ws.get("description", ""),
        "sequence": ws.get("sequence", 0),
        "is_hidden": ws.get("is_hidden", False),
        "roles": ws.get("roles", ""),
        "widgets": ws.get("widgets") or [],
        "items": items,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


def _get_ws_obj(ws_data: dict[str, Any]) -> Any:
    # Wrap dict in controller if needed
    if isinstance(ws_data, dict):
        ws_cls = document_registry.get("WorkspaceSidebar")
        if ws_cls:
            return ws_cls(
                "WorkspaceSidebar", ws_data, grunt._require_user(), grunt._require_session()
            )
    return ws_data


@router.get("/")
async def list_workspaces() -> dict[str, Any]:
    """List workspaces visible to the current user."""
    all_ws = await grunt.get_list(
        "WorkspaceSidebar",
        fields=["name"],
        order_by="sequence",
    )

    data = []
    user = grunt.session
    for ws_brief in all_ws:
        try:
            ws_data = await grunt.get_doc("WorkspaceSidebar", ws_brief["name"])
        except Exception:
            continue
        if not ws_data:
            continue
        ws = _get_ws_obj(ws_data)

        if ws_data.get("is_hidden") and not user.is_superadmin:
            continue
        if hasattr(ws, "has_access") and not ws.has_access(user):
            continue

        data.append(_workspace_to_dict(ws_data))

    return {"success": True, "data": data}


@router.get("/{name}")
async def get_workspace(
    name: str,
) -> dict[str, Any]:
    """Get a single workspace with filtered items."""
    try:
        ws_data = await grunt.get_doc("WorkspaceSidebar", name)
    except HTTPException as err:
        if err.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено") from err
        raise
    except Exception as err:
        logger.error("workspace.get_doc_failed", name=name, error=str(err))
        raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено") from err

    if not ws_data:
        logger.error("workspace.get_doc_returned_none", name=name)
        raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")

    ws = _get_ws_obj(ws_data)

    if hasattr(ws, "has_access") and not ws.has_access(grunt.session):
        raise HTTPException(status_code=403, detail="Немає доступу до цього workspace")

    return {"success": True, "data": _workspace_to_dict(ws_data)}


@router.post("/", status_code=201)
async def create_workspace(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Create a new workspace."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    data = body.copy()
    if "items" in data:
        data["sidebar_items"] = data.pop("items")

    ws_data = await grunt.new_doc("WorkspaceSidebar", data)
    return {"success": True, "data": _workspace_to_dict(ws_data)}


@router.put("/{name}")
async def update_workspace(
    name: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Update a workspace."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    data = body.copy()
    if "items" in data:
        data["sidebar_items"] = data.pop("items")

    ws_data = await grunt.save_doc("WorkspaceSidebar", name, data)
    return {"success": True, "data": _workspace_to_dict(ws_data)}


@router.delete("/{name}")
async def delete_workspace(
    name: str,
) -> dict[str, Any]:
    """Delete a workspace."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    await grunt.delete_doc("WorkspaceSidebar", name)
    return {"success": True, "data": {"deleted": name}}


@router.get("/{name}/counts")
async def workspace_counts(
    name: str,
) -> dict[str, Any]:
    """Get document counts for workspace links."""
    try:
        ws_data = await grunt.get_doc("WorkspaceSidebar", name)
    except HTTPException as err:
        if err.status_code == 404:
            raise HTTPException(status_code=404, detail="Workspace found") from err
        raise

    ws = _get_ws_obj(ws_data)

    counts = await ws.get_counts() if hasattr(ws, "get_counts") else {}
    return {"success": True, "data": counts}


@router.get("/{name}/widget-data")
async def workspace_widget_data(
    name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> dict[str, Any]:
    """Compute widget data for all widgets in a workspace."""
    try:
        ws_data = await grunt.get_doc("WorkspaceSidebar", name)
    except HTTPException as err:
        if err.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено") from err
        raise

    ws = _get_ws_obj(ws_data)

    if hasattr(ws, "has_access") and not ws.has_access(grunt.session):
        raise HTTPException(status_code=403, detail="Немає доступу до цього workspace")

    global_since: datetime | None = None
    global_until: datetime | None = None
    if date_from:
        with contextlib.suppress(ValueError):
            global_since = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
    if date_to:
        with contextlib.suppress(ValueError):
            global_until = datetime.fromisoformat(date_to).replace(tzinfo=UTC)

    data = (
        await ws.get_widget_data(date_from=global_since, date_to=global_until)
        if hasattr(ws, "get_widget_data")
        else {}
    )
    return {"success": True, "data": data}
