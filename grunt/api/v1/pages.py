"""Pages whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt

_PAGE_FIELDS = [
    "name",
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


@grunt.whitelist()
async def list_pages() -> list[dict[str, Any]]:
    """List all registered custom pages."""
    return await grunt.get_list(
        "Page", limit=1000, order_by="sidebar_order", order="asc", fields=_PAGE_FIELDS
    )


@grunt.whitelist(roles=["superadmin"])
async def register_page(page_data: dict[str, Any]) -> dict[str, Any]:
    """Register or update a custom page from an app. Admin only."""
    route = (page_data.get("route") or "").strip()
    if not route:
        grunt.throw("route є обов'язковим", "VALIDATION_ERROR")

    existing = await grunt.get_list("Page", filters={"route": route}, limit=1)
    page_id = existing[0]["name"] if existing else None
    update_data = {k: v for k, v in page_data.items() if k in _PAGE_UPDATABLE}

    if page_id:
        doc = await grunt.save_doc("Page", page_id, update_data)
    else:
        doc = await grunt.new_doc("Page", {"route": route, **update_data})

    return {"route": route, "title": doc.get("title", route)}


@grunt.whitelist(roles=["superadmin"])
async def delete_page(route: str) -> bool:
    """Remove a custom page registration. Admin only."""
    if not route.startswith("/"):
        route = f"/{route}"
    existing = await grunt.get_list("Page", filters={"route": route}, limit=1)
    if not existing:
        grunt.throw("Сторінку не знайдено", "NOT_FOUND")

    await grunt.delete_doc("Page", existing[0]["name"])
    return True
