"""Pages API — register and list custom app pages."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

router = APIRouter()


def _page_table():
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    return compile_doctype_to_table(doctype_registry._doctypes["Page"])


@router.get("/")
async def list_pages(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """List all registered custom pages."""
    table = _page_table()
    result = await session.execute(select(table).order_by(table.c.sidebar_order))
    pages = result.mappings().all()
    return {
        "success": True,
        "data": [
            {
                "id": p["id"],
                "route": p["route"],
                "title": p["title"],
                "icon": p["icon"],
                "component": p["component"],
                "app": p["app"],
                "sidebar_section": p["sidebar_section"],
                "sidebar_order": p["sidebar_order"],
                "is_default_home": bool(p["is_default_home"]),
            }
            for p in pages
        ],
    }


@router.post("/")
async def register_page(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Register a custom page from an app."""
    route = body.get("route", "")
    if not route:
        raise HTTPException(status_code=422, detail="route є обов'язковим")

    table = _page_table()
    existing = (await session.execute(
        select(table).where(table.c.route == route)
    )).mappings().first()

    if existing:
        await session.execute(
            update(table)
            .where(table.c.route == route)
            .values(
                title=body.get("title", existing["title"]),
                icon=body.get("icon", existing["icon"]),
                component=body.get("component", existing["component"]),
                app=body.get("app", existing["app"]),
                sidebar_section=body.get("sidebar_section", existing["sidebar_section"]),
                sidebar_order=body.get("sidebar_order", existing["sidebar_order"]),
                is_default_home=body.get("is_default_home", existing["is_default_home"]),
                modified_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
        return {"success": True, "data": {"route": route, "title": body.get("title", existing["title"])}}

    page_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await session.execute(
        table.insert().values(
            id=page_id,
            name=route,
            owner="system",
            created_at=now,
            modified_at=now,
            modified_by="system",
            docstatus=0,
            route=route,
            title=body.get("title", route),
            icon=body.get("icon"),
            component=body.get("component", ""),
            app=body.get("app", ""),
            sidebar_section=body.get("sidebar_section"),
            sidebar_order=body.get("sidebar_order", 0),
            is_default_home=body.get("is_default_home", False),
        )
    )
    await session.flush()
    return {"success": True, "data": {"route": route, "title": body.get("title", route)}}


@router.delete("/{route:path}")
async def delete_page(
    route: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Remove a custom page registration."""
    table = _page_table()
    full_route = f"/{route}"
    existing = (await session.execute(
        select(table).where(table.c.route == full_route)
    )).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Сторінку не знайдено")
    await session.execute(delete(table).where(table.c.route == full_route))
    await session.flush()
    return {"success": True, "message": "Сторінку видалено"}
