"""Pages whitelisted methods."""

from typing import Any

from grunt.api.context import whitelist
from grunt.errors import throw
from grunt.i18n import _
lazy from grunt.document.api import documents

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


@whitelist()
async def list_pages() -> list[dict[str, Any]]:
    """List all registered custom pages."""
    return await documents.get_list(
        "Page", limit=1000, order_by="sidebar_order", order="asc", fields=_PAGE_FIELDS
    )


@whitelist(roles=["System Manager"])
async def register_page(page_data: dict[str, Any]) -> dict[str, Any]:
    """Register or update a custom page from an app. Admin only."""
    route = (page_data.get("route") or "").strip()
    if not route:
        throw(_("route is required"), "VALIDATION_ERROR")

    existing = await documents.get_list("Page", filters={"route": route}, limit=1)
    page_id = existing[0]["name"] if existing else None
    update_data = {k: v for k, v in page_data.items() if k in _PAGE_UPDATABLE}

    if page_id:
        doc = await documents.save_doc("Page", page_id, update_data)
    else:
        doc = await documents.new_doc("Page", {"route": route, **update_data})

    return {"route": route, "title": doc.get("title", route)}


@whitelist(roles=["System Manager"])
async def delete_page(route: str) -> bool:
    """Remove a custom page registration. Admin only."""
    if not route.startswith("/"):
        route = f"/{route}"
    existing = await documents.get_list("Page", filters={"route": route}, limit=1)
    if not existing:
        throw(_("Page not found"), "NOT_FOUND")

    await documents.delete_doc("Page", existing[0]["name"])
    return True
