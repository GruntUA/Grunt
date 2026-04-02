"""Workspace API — CRUD and counts for workspace navigation."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.db.system_tables import GruntWorkspace, GruntWorkspaceLink
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _workspace_to_dict(ws: GruntWorkspace) -> dict[str, Any]:
    return {
        "name": ws.name,
        "label": ws.label,
        "app": ws.app,
        "icon": ws.icon,
        "color": ws.color,
        "description": ws.description,
        "sequence": ws.sequence,
        "is_hidden": ws.is_hidden,
        "roles": ws.roles,
        "items": [
            {
                "section": item.section,
                "type": item.type,
                "label": item.label,
                "icon": item.icon,
                "link_to": item.link_to,
                "show_count": item.show_count,
                "count_filters": item.count_filters,
                "show_new_btn": item.show_new_btn,
                "roles": item.roles,
                "sequence": item.sequence,
                "is_singleton": (
                    doctype_registry._doctypes[item.link_to].is_singleton
                    if item.type == "DocType" and item.link_to in doctype_registry._doctypes
                    else False
                ),
            }
            for item in sorted(ws.items, key=lambda i: i.sequence)
        ],
    }


def _user_has_workspace_access(ws: GruntWorkspace, user: GruntUser) -> bool:
    if user.is_superadmin:
        return True
    if not ws.roles:
        return True
    allowed = {r.strip() for r in ws.roles.split(",") if r.strip()}
    return bool(allowed & set(user.roles))


def _user_has_link_access(link: dict[str, Any], user: GruntUser) -> bool:
    if user.is_superadmin:
        return True
    roles_str = link.get("roles", "")
    if not roles_str:
        return True
    allowed = {r.strip() for r in roles_str.split(",") if r.strip()}
    return bool(allowed & set(user.roles))


def _filter_items_by_role(items: list[dict[str, Any]], user: GruntUser) -> list[dict[str, Any]]:
    return [item for item in items if _user_has_link_access(item, user)]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/")
async def list_workspaces(
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """List workspaces visible to the current user, sorted by sequence."""
    result = await session.execute(
        select(GruntWorkspace).order_by(GruntWorkspace.sequence)
    )
    all_ws = result.scalars().all()

    data = []
    for ws in all_ws:
        if ws.is_hidden and not user.is_superadmin:
            continue
        if not _user_has_workspace_access(ws, user):
            continue
        ws_dict = _workspace_to_dict(ws)
        ws_dict["items"] = _filter_items_by_role(ws_dict["items"], user)
        data.append(ws_dict)

    return {"success": True, "data": data}


@router.get("/{name}")
async def get_workspace(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Get a single workspace with items filtered by user roles."""
    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == name)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")
    if not _user_has_workspace_access(ws, user):
        raise HTTPException(status_code=403, detail="Немає доступу до цього workspace")

    ws_dict = _workspace_to_dict(ws)
    ws_dict["items"] = _filter_items_by_role(ws_dict["items"], user)
    return {"success": True, "data": ws_dict}


@router.post("/", status_code=201)
async def create_workspace(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Create a new workspace (superadmin only)."""
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name обов'язковий")

    existing = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Workspace '{name}' вже існує")

    ws = GruntWorkspace(
        id=str(uuid.uuid4()),
        name=name,
        label=body.get("label", name),
        app=body.get("app", ""),
        icon=body.get("icon", "📁"),
        color=body.get("color", "#2D6A4F"),
        description=body.get("description", ""),
        sequence=body.get("sequence", 0),
        is_hidden=body.get("is_hidden", False),
        roles=body.get("roles", ""),
    )
    session.add(ws)

    for item_data in body.get("items", []):
        link = GruntWorkspaceLink(
            id=str(uuid.uuid4()),
            workspace_id=ws.id,
            section=item_data.get("section", ""),
            type=item_data.get("type", "DocType"),
            label=item_data.get("label", ""),
            icon=item_data.get("icon", ""),
            link_to=item_data.get("link_to", ""),
            show_count=item_data.get("show_count", False),
            count_filters=item_data.get("count_filters", ""),
            show_new_btn=item_data.get("show_new_btn", False),
            roles=item_data.get("roles", ""),
            sequence=item_data.get("sequence", 0),
        )
        session.add(link)

    await session.commit()
    await session.refresh(ws)
    return {"success": True, "data": _workspace_to_dict(ws)}


@router.put("/{name}")
async def update_workspace(
    name: str,
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Update a workspace (superadmin only). Replaces items entirely."""
    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == name)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")

    for field in ("label", "app", "icon", "color", "description", "sequence", "is_hidden", "roles"):
        if field in body:
            setattr(ws, field, body[field])

    if "items" in body:
        # Delete old items and replace
        await session.execute(
            delete(GruntWorkspaceLink).where(GruntWorkspaceLink.workspace_id == ws.id)
        )
        for item_data in body["items"]:
            link = GruntWorkspaceLink(
                id=str(uuid.uuid4()),
                workspace_id=ws.id,
                section=item_data.get("section", ""),
                type=item_data.get("type", "DocType"),
                label=item_data.get("label", ""),
                icon=item_data.get("icon", ""),
                link_to=item_data.get("link_to", ""),
                show_count=item_data.get("show_count", False),
                count_filters=item_data.get("count_filters", ""),
                show_new_btn=item_data.get("show_new_btn", False),
                roles=item_data.get("roles", ""),
                sequence=item_data.get("sequence", 0),
            )
            session.add(link)

    await session.commit()
    await session.refresh(ws)
    return {"success": True, "data": _workspace_to_dict(ws)}


@router.delete("/{name}")
async def delete_workspace(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Delete a workspace (superadmin only)."""
    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == name)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")

    await session.delete(ws)
    await session.commit()
    return {"success": True, "data": {"deleted": name}}


@router.get("/{name}/counts")
async def workspace_counts(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Get document counts for workspace links that have show_count=true."""
    result = await session.execute(
        select(GruntWorkspace).where(GruntWorkspace.name == name)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace '{name}' не знайдено")

    counts: dict[str, int] = {}

    for item in ws.items:
        if not item.show_count or item.type != "DocType":
            continue

        try:
            dt = await doctype_registry.get(item.link_to)
        except HTTPException:
            continue

        from grunt.core.metadata.compiler import get_table_name  # noqa: PLC0415

        table_name = get_table_name(dt.module, dt.name)

        try:
            # Build count query
            count_sql = f"SELECT COUNT(*) FROM \"{table_name}\""  # noqa: S608

            if item.count_filters:
                try:
                    filters = json.loads(item.count_filters)
                    if isinstance(filters, dict) and filters:
                        conditions = []
                        for col, val in filters.items():
                            # Parameterized via text() bind params
                            conditions.append(f"\"{col}\" = :{col}")
                        count_sql += " WHERE " + " AND ".join(conditions)
                        result_count = await session.execute(
                            text(count_sql), filters
                        )
                    else:
                        result_count = await session.execute(text(count_sql))
                except (json.JSONDecodeError, ValueError):
                    result_count = await session.execute(text(count_sql))
            else:
                result_count = await session.execute(text(count_sql))

            count_val = result_count.scalar() or 0

            # Build key: use link_to + suffix if filters exist
            key = item.link_to
            if item.count_filters:
                try:
                    f = json.loads(item.count_filters)
                    if isinstance(f, dict):
                        suffix = "_".join(str(v).lower() for v in f.values())
                        key = f"{item.link_to}_{suffix}"
                except (json.JSONDecodeError, ValueError):
                    logger.debug(
                        "workspace.count_key_suffix_parse_error",
                        link_to=item.link_to,
                        count_filters=item.count_filters,
                    )

            counts[key] = count_val

        except Exception as e:
            logger.warning("workspace.count_error", link_to=item.link_to, error=str(e))
            continue

    return {"success": True, "data": counts}
