"""Workspace whitelisted methods."""

from __future__ import annotations

from typing import Any

import structlog

import grunt
from grunt.document.registry import document_registry

logger = structlog.get_logger()


def _workspace_to_dict(ws_data: Any) -> dict[str, Any]:
    """Convert AppMenu document data to dict, filtering items by role."""
    from grunt.app import grunt as grunt_app

    user = grunt_app._require_user()

    items = []
    sidebar_items = ws_data.get("sidebar_items") or []
    for item in sorted(sidebar_items, key=lambda i: i.get("idx", 0)):
        item_roles = item.get("roles", "")
        if not user.is_superadmin and item_roles:
            allowed = {r.strip() for r in item_roles.split(",") if r.strip()}
            if not (allowed & set(user.roles)):
                continue

        item_type = item.get("type", "DocType")
        link_to = item.get("link_to", "")
        is_singleton = False
        if item_type == "DocType" and link_to:
            from grunt.metadata.registry import doctype_registry

            if link_to in doctype_registry._doctypes:
                is_singleton = doctype_registry._doctypes[link_to].is_singleton

        items.append(
            {
                "section": item.get("section", ""),
                "type": item_type,
                "label": item.get("label", ""),
                "icon": item.get("icon", ""),
                "link_to": link_to,
                "show_count": item.get("show_count", False),
                "show_new_btn": item.get("show_new_btn", False),
                "roles": item_roles,
                "sequence": item.get("idx", 0),
                "is_singleton": is_singleton,
            }
        )

    return {
        "name": ws_data.get("name"),
        "label": ws_data.get("label"),
        "app": ws_data.get("app", ""),
        "icon": ws_data.get("icon", "📁"),
        "color": ws_data.get("color", "#2D6A4F"),
        "description": ws_data.get("description", ""),
        "sequence": ws_data.get("sequence", 0),
        "is_hidden": ws_data.get("is_hidden", False),
        "roles": ws_data.get("roles", ""),
        "home_page": ws_data.get("home_page") or None,
        "items": items,
    }


async def _get_ws_controller(name: str) -> Any:
    doc_data = await grunt.get_doc("AppMenu", name)
    if not doc_data:
        grunt.throw(f"Workspace '{name}' не знайдено", "NOT_FOUND")

    ws_cls = document_registry.get("AppMenu")
    if ws_cls:
        from grunt.app import grunt as grunt_app

        return ws_cls("AppMenu", doc_data, grunt_app._require_user(), grunt_app._require_session())
    return doc_data


@grunt.whitelist()
async def list_workspaces() -> list[dict[str, Any]]:
    """List workspaces visible to the current user."""
    all_ws = await grunt.get_list("AppMenu", fields=["name"], order_by="sequence")
    data = []
    user = await grunt.get_current_user()
    if not user:
        return []

    for ws_brief in all_ws:
        try:
            ws_data = await grunt.get_doc("AppMenu", ws_brief["name"])
            if ws_data.get("is_hidden") and not user.is_superadmin:
                continue
            # Basic role check could be added here
            data.append(_workspace_to_dict(ws_data))
        except Exception:
            continue
    return data


@grunt.whitelist()
async def get_workspace(name: str) -> dict[str, Any]:
    """Get a single workspace with filtered items."""
    ws_data = await grunt.get_doc("AppMenu", name)
    if not ws_data:
        grunt.throw("Not found", "NOT_FOUND")
    return _workspace_to_dict(ws_data)


@grunt.whitelist()
async def save_workspace(workspace_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a workspace. Admin only."""
    from grunt.app import grunt as grunt_app

    if not grunt_app._require_user().is_superadmin:
        grunt.throw("Not authorized", "PERMISSION_DENIED")

    data = workspace_data.copy()
    if "items" in data:
        data["sidebar_items"] = data.pop("items")

    name = data.get("name")
    if name:
        ws_data = await grunt.save_doc("AppMenu", name, data)
    else:
        ws_data = await grunt.new_doc("AppMenu", data)

    return _workspace_to_dict(ws_data)


@grunt.whitelist()
async def delete_workspace(name: str) -> bool:
    """Delete a workspace. Admin only."""
    from grunt.app import grunt as grunt_app

    if not grunt_app._require_user().is_superadmin:
        grunt.throw("Not authorized", "PERMISSION_DENIED")
    await grunt.delete_doc("AppMenu", name)
    return True


@grunt.whitelist()
async def get_counts(name: str) -> dict[str, int]:
    """Get document counts for workspace links."""
    ws = await _get_ws_controller(name)
    if hasattr(ws, "get_counts"):
        return await ws.get_counts()
    return {}
