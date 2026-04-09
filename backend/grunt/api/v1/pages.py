"""Pages API — register and list custom app pages."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from grunt.api.router import GruntRouter
from grunt.app import grunt

router = GruntRouter(prefix="/pages", tags=["pages"])


_PAGE_FIELDS = [
    "id",
    "route",
    "title",
    "icon",
    "component",
    "app",
    "sidebar_section",
    "sidebar_order",
    "is_default_home",
]

_PAGE_UPDATABLE = {
    "title",
    "icon",
    "component",
    "app",
    "sidebar_section",
    "sidebar_order",
    "is_default_home",
}


@router.get("/")
async def list_pages() -> dict[str, Any]:
    """List all registered custom pages."""
    data = await grunt.get_list(
        "Page",
        limit=10000,
        order_by="sidebar_order",
        order="asc",
        fields=_PAGE_FIELDS,
    )
    return {"success": True, "data": data}


@router.post("/")
async def register_page(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Register or update a custom page from an app."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    route = (body.get("route") or "").strip()
    if not route:
        raise HTTPException(status_code=422, detail="route є обов'язковим")

    existing = await grunt.get_list("Page", filters={"route": route}, limit=1)
    page_id = existing[0]["id"] if existing else None
    update_data = {k: v for k, v in body.items() if k in _PAGE_UPDATABLE}

    if page_id:
        doc = await grunt.save_doc("Page", page_id, update_data)
    else:
        doc = await grunt.new_doc("Page", {"route": route, **update_data})

    return {"success": True, "data": {"route": route, "title": doc.get("title", route)}}


@router.delete("/{route:path}")
async def delete_page(
    route: str,
) -> dict[str, Any]:
    """Remove a custom page registration."""
    if not grunt.session.is_superadmin:
        raise HTTPException(status_code=403, detail="Not authorized")

    full_route = f"/{route}"
    existing = await grunt.get_list("Page", filters={"route": full_route}, limit=1)
    page_id = existing[0]["id"] if existing else None

    if not page_id:
        raise HTTPException(status_code=404, detail="Сторінку не знайдено")

    await grunt.delete_doc("Page", page_id)
    return {"success": True, "message": "Сторінку видалено"}
