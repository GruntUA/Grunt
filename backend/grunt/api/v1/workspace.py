"""Workspace API — CRUD and counts for workspace navigation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from grunt.app import grunt
from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_engine, get_session
from grunt.core.document.registry import document_registry
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _workspace_to_dict(ws: Any, user: GruntUser) -> dict[str, Any]:
    """Convert WorkspaceSidebar document to dict, filtering items by role."""
    items = []
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
                # We can't easily await here in a sync list comp if we were using it,
                # but we are in a loop. However, doctype_registry is often sync-cached.
                from grunt.core.metadata.registry import doctype_registry
                if link_to in doctype_registry._doctypes:
                    is_singleton = doctype_registry._doctypes[link_to].is_singleton
            except Exception:
                pass

        items.append({
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
        })

    return {
        "name": ws.name,
        "label": ws.label,
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


@router.get("/")
async def list_workspaces(
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """List workspaces visible to the current user."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        all_ws = await grunt.get_list(
            "WorkspaceSidebar",
            fields=["*"],
            order_by="sequence",
        )

        data = []
        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        for ws_data in all_ws:
            # We need the full doc to use has_access and child tables
            ws_dict = await grunt.get_doc("WorkspaceSidebar", ws_data["name"])
            ws = WorkspaceSidebar("WorkspaceSidebar", ws_dict, user, session)
            
            if ws.get("is_hidden") and not user.is_superadmin:
                continue
            if not ws.has_access(user):
                continue
            data.append(_workspace_to_dict(ws, user))

        return {"success": True, "data": data}
    finally:
        grunt.reset_context(_tokens)


@router.get("/{name}")
async def get_workspace(
    name: str,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Get a single workspace with filtered items."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        try:
            ws_dict = await grunt.get_doc("WorkspaceSidebar", name)
        except HTTPException:
            raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")
        
        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        ws = WorkspaceSidebar("WorkspaceSidebar", ws_dict, user, session)

        if not ws.has_access(user):
            raise HTTPException(status_code=403, detail="Немає доступу до цього workspace")

        return {"success": True, "data": _workspace_to_dict(ws, user)}
    finally:
        grunt.reset_context(_tokens)


@router.post("/", status_code=201)
async def create_workspace(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Create a new workspace."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        # Convert items to child table format if needed
        data = body.copy()
        if "items" in data:
            data["sidebar_items"] = data.pop("items")

        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        ws = WorkspaceSidebar("WorkspaceSidebar", data, user, session)
        await ws.insert()
        return {"success": True, "data": _workspace_to_dict(ws, user)}
    finally:
        grunt.reset_context(_tokens)


@router.put("/{name}")
async def update_workspace(
    name: str,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Update a workspace."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        ws_dict = await grunt.get_doc("WorkspaceSidebar", name)
        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        ws = WorkspaceSidebar("WorkspaceSidebar", ws_dict, user, session)
        
        data = body.copy()
        if "items" in data:
            data["sidebar_items"] = data.pop("items")
        
        ws.update(data)
        await ws.save()
        return {"success": True, "data": _workspace_to_dict(ws, user)}
    finally:
        grunt.reset_context(_tokens)


@router.delete("/{name}")
async def delete_workspace(
    name: str,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Delete a workspace."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        ws_dict = await grunt.get_doc("WorkspaceSidebar", name)
        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        ws = WorkspaceSidebar("WorkspaceSidebar", ws_dict, user, session)
        await ws.delete()
        return {"success": True, "data": {"deleted": name}}
    finally:
        grunt.reset_context(_tokens)


@router.get("/{name}/counts")
async def workspace_counts(
    name: str,
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Get document counts for workspace links."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        try:
            ws_dict = await grunt.get_doc("WorkspaceSidebar", name)
        except HTTPException:
            raise HTTPException(status_code=404, detail="Workspace found")
        
        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        ws = WorkspaceSidebar("WorkspaceSidebar", ws_dict, user, session)
        
        counts = await ws.get_counts()
        return {"success": True, "data": counts}
    finally:
        grunt.reset_context(_tokens)


@router.get("/{name}/widget-data")
async def workspace_widget_data(
    name: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Compute widget data for all widgets in a workspace."""
    _tokens = grunt.set_context(session, engine, user)
    try:
        try:
            ws_dict = await grunt.get_doc("WorkspaceSidebar", name)
        except HTTPException:
            raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")
        
        WorkspaceSidebar = document_registry.get("WorkspaceSidebar")
        ws = WorkspaceSidebar("WorkspaceSidebar", ws_dict, user, session)
        
        if not ws.has_access(user):
            raise HTTPException(status_code=403, detail="Немає доступу до цього workspace")

        global_since: datetime | None = None
        global_until: datetime | None = None
        if date_from:
            try:
                global_since = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        if date_to:
            try:
                global_until = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        data = await ws.get_widget_data(date_from=global_since, date_to=global_until)
        return {"success": True, "data": data}
    finally:
        grunt.reset_context(_tokens)
