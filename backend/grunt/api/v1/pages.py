"""Pages API — register and list custom app pages."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.db.system_tables import GruntPage

router = APIRouter()


@router.get("/")
async def list_pages(
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """List all registered custom pages."""
    result = await session.execute(
        select(GruntPage).order_by(GruntPage.sidebar_order)
    )
    pages = result.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": p.id,
                "route": p.route,
                "title": p.title,
                "icon": p.icon,
                "component": p.component,
                "app": p.app,
                "sidebar_section": p.sidebar_section,
                "sidebar_order": p.sidebar_order,
                "is_default_home": bool(p.is_default_home),
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

    existing = await session.execute(
        select(GruntPage).where(GruntPage.route == route)
    )
    if existing.scalar_one_or_none():
        # Update existing
        page = (
            await session.execute(
                select(GruntPage).where(GruntPage.route == route)
            )
        ).scalar_one()
        page.title = body.get("title", page.title)
        page.icon = body.get("icon", page.icon)
        page.component = body.get("component", page.component)
        page.app = body.get("app", page.app)
        page.sidebar_section = body.get("sidebar_section", page.sidebar_section)
        page.sidebar_order = body.get("sidebar_order", page.sidebar_order)
        page.is_default_home = body.get("is_default_home", page.is_default_home)
        await session.flush()
        return {"success": True, "data": {"route": page.route, "title": page.title}}

    page = GruntPage(
        route=route,
        title=body.get("title", route),
        icon=body.get("icon"),
        component=body.get("component", ""),
        app=body.get("app", ""),
        sidebar_section=body.get("sidebar_section"),
        sidebar_order=body.get("sidebar_order", 0),
        is_default_home=body.get("is_default_home", False),
    )
    session.add(page)
    await session.flush()
    return {"success": True, "data": {"route": page.route, "title": page.title}}


@router.delete("/{route:path}")
async def delete_page(
    route: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    """Remove a custom page registration."""
    result = await session.execute(
        select(GruntPage).where(GruntPage.route == f"/{route}")
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Сторінку не знайдено")
    await session.delete(page)
    await session.flush()
    return {"success": True, "message": "Сторінку видалено"}
