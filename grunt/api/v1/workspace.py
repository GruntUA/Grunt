"""Workspace whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt.site.doctypes.AppMenu.app_menu import AppMenu


async def _workspace_to_dict(ws_data: Any) -> dict[str, Any]:
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
        item_icon = item.get("icon", "")
        is_singleton = False
        if item_type == "DocType" and link_to:
            from grunt.metadata.registry import doctype_registry

            try:
                dt_meta = await doctype_registry.get(link_to)
            except Exception:
                dt_meta = None
            if dt_meta is not None:
                is_singleton = dt_meta.is_singleton
                # Fall back to the DocType's own icon when the sidebar item
                # doesn't pin one explicitly.
                if not item_icon:
                    item_icon = dt_meta.icon or ""

        items.append(
            {
                "section": item.get("section", ""),
                "type": item_type,
                "label": item.get("label", ""),
                "icon": item_icon,
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


async def _get_ws_controller(name: str) -> AppMenu:
    # Precisely-typed overloads live on the GruntApp instance (grunt.app.grunt) —
    # the top-level `grunt` package facade's stub can't use `@overload` (mypy
    # requires a real implementation for that in a non-stub .py file), so it
    # falls back to a looser `dict[str, Any] | D` union that doesn't narrow here.
    from grunt.app import grunt as grunt_app

    return await grunt_app.get_doc(AppMenu, name)


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
            data.append(await _workspace_to_dict(ws_data))
        except Exception:
            continue
    return data


@grunt.whitelist()
async def get_workspace(name: str) -> dict[str, Any]:
    """Get a single workspace with filtered items."""
    ws_data = await _get_ws_controller(name)
    return await _workspace_to_dict(ws_data)


@grunt.whitelist(roles=["superadmin"])
async def save_workspace(workspace_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a workspace. Admin only."""
    data = workspace_data.copy()
    if "items" in data:
        data["sidebar_items"] = data.pop("items")

    name = data.get("name")
    if name:
        ws_data = await grunt.save_doc("AppMenu", name, data)
    else:
        ws_data = await grunt.new_doc("AppMenu", data)

    return await _workspace_to_dict(ws_data)


@grunt.whitelist(roles=["superadmin"])
async def delete_workspace(name: str) -> bool:
    """Delete a workspace. Admin only."""
    await grunt.delete_doc("AppMenu", name)
    return True


@grunt.whitelist()
async def get_counts(name: str) -> dict[str, int]:
    """Get document counts for workspace links."""
    ws = await _get_ws_controller(name)
    if hasattr(ws, "get_counts"):
        return await ws.get_counts()
    return {}


# Cached because the stat costs one COUNT per business doctype (dozens of
# queries) while being a purely informational figure on the home page.
_DOC_STATS_TTL_SECONDS = 60.0
_doc_stats_cache: dict[tuple[str, str], tuple[float, dict[str, int]]] = {}


@grunt.whitelist()
async def get_document_stats() -> dict[str, int]:
    """Return an honest, deduplicated document total for the home page.

    Unlike summing per-workspace sidebar counts (which double-counts doctypes
    shared across workspaces and is dominated by log/session churn), this counts
    each business doctype exactly once and excludes infrastructural doctypes
    (logs, sessions, versions, queues, config/metadata).

    ``grunt.count`` is permission-aware, so the figure only ever covers rows
    the caller may see — the cache key is therefore per (site, user), for a
    minute; an approximate headline number is not worth dozens of COUNT
    queries on every page load.
    """
    import time

    from grunt.activity import FEED_HIDDEN_DOCTYPES
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager

    try:
        site = site_manager.get_active_site()
    except Exception:
        site = ""

    user = await grunt.get_current_user()
    cache_key = (site, getattr(user, "email", ""))

    now = time.monotonic()
    cached = _doc_stats_cache.get(cache_key)
    if cached and now - cached[0] < _DOC_STATS_TTL_SECONDS:
        return cached[1]

    total = 0
    counted = 0
    for dt in await doctype_registry.list_all():
        if dt.is_child or dt.is_virtual or dt.is_singleton:
            continue
        if dt.name in FEED_HIDDEN_DOCTYPES:
            continue
        try:
            total += await grunt.count(dt.name, respect_permissions=True)
            counted += 1
        except Exception:
            # A doctype without a physical table yet — skip it silently.
            continue

    stats = {"total": total, "doctypes": counted}
    _doc_stats_cache[cache_key] = (now, stats)
    return stats

@grunt.whitelist()
async def get_my_work() -> dict[str, Any]:
    """Return the current user's personal work items for the home page:

    open tasks assigned to them (flagged when overdue) and unread notifications.
    """
    from datetime import date

    from grunt.app import grunt as grunt_app

    user = grunt_app._require_user()
    email = user.email
    today = date.today().isoformat()

    # Open tasks assigned to me.
    try:
        todos = await grunt.get_list(
            "ToDo",
            filters={"assigned_to": email, "status": "Open"},
            fields=[
                "name",
                "description",
                "reference_doctype",
                "reference_id",
                "due_date",
                "priority",
            ],
            order_by="due_date",
            order="asc",
            limit=50,
        )
    except Exception:
        todos = []

    from grunt.document.titles import resolve_reference_titles

    titles = await resolve_reference_titles(
        [(t.get("reference_doctype") or "", t.get("reference_id") or "") for t in todos]
    )

    assigned: list[dict[str, Any]] = []
    overdue = 0
    for t in todos:
        ref_dt = t.get("reference_doctype") or ""
        ref_id = t.get("reference_id") or ""
        due = t.get("due_date")
        is_overdue = bool(due) and str(due) < today
        if is_overdue:
            overdue += 1
        assigned.append(
            {
                "id": t.get("name"),
                "description": t.get("description"),
                "reference_doctype": ref_dt,
                "reference_id": ref_id,
                "title": titles.get((ref_dt, ref_id)) or ref_id or t.get("description"),
                "due_date": due,
                "priority": t.get("priority"),
                "overdue": is_overdue,
            }
        )

    # Unread notifications.
    try:
        notifications = await grunt.get_list(
            "Notification",
            filters={"user": email, "is_read": False},
            fields=["name", "subject", "doctype", "doc_id", "created_at"],
            order_by="created_at",
            order="desc",
            limit=20,
        )
    except Exception:
        notifications = []

    return {
        "assigned": assigned,
        "notifications": notifications,
        "counts": {
            "assigned": len(assigned),
            "overdue": overdue,
            "unread": len(notifications),
        },
    }
