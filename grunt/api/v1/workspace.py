"""Workspace whitelisted methods."""

from datetime import date
from typing import Any

import grunt
from grunt.api.v1.dashboard import page_visible
from grunt.document.titles import resolve_reference_titles
from grunt.metadata.registry import doctype_registry
from grunt.site.doctypes.AppMenu.app_menu import AppMenu, count_key, parse_count_filters
from grunt.site.settings import get_setting


async def _visible_pages() -> list[dict[str, Any]]:
    """Pages the current user may open, as dashboard candidates for the apps."""
    user = grunt.get_user()
    pages = await grunt.get_list(
        "Page",
        fields=["name", "label", "app", "is_published", "roles"],
        limit=1000,
        include_total=False,
    )
    visible = [p for p in pages if page_visible(p, user)]
    return sorted(visible, key=lambda p: str(p.get("label") or p["name"]).casefold())


def _dashboards(ws_data: Any, pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The app's dashboards for the switcher on its home: the home page first,
    then the other pages of the same app, each only if the user may open it."""
    home = ws_data.get("home_page")
    app = ws_data.get("app")
    picked = [p for p in pages if p["name"] == home]
    picked += [p for p in pages if app and p.get("app") == app and p["name"] != home]
    return [{"name": p["name"], "label": p.get("label") or p["name"]} for p in picked]


def _sections(ws_data: Any, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The sidebar sections in item order, each with its icon: the one set in
    the app's Sections table, else the icon of the section's first item."""
    icons = {
        (row.get("section") or "").strip(): row.get("icon") or ""
        for row in ws_data.get("sections") or []
    }
    sections: list[dict[str, str]] = []
    for item in items:
        name = item["section"]
        if name and item["type"] != "Divider" and all(s["section"] != name for s in sections):
            sections.append({"section": name, "icon": icons.get(name) or item["icon"]})
    return sections


async def _sidebar_mode(ws_data: Any, sections: list[dict[str, str]]) -> str:
    """Sidebar mode: "sections" (collapsible groups) or "modules" (items open
    beside the sidebar). Auto picks modules from SystemSettings.sidebar_modules_after
    sections on."""
    style = ws_data.get("sidebar_style") or "Auto"
    if style == "Auto":
        threshold = int(await get_setting("sidebar_modules_after", 6) or 6)
        return "modules" if len(sections) >= threshold else "sections"
    return "modules" if style == "Modules" else "sections"


async def _workspace_to_dict(
    ws_data: Any, pages: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Convert AppMenu document data to dict, filtering items by role."""

    user = grunt.get_user()
    if pages is None:
        pages = await _visible_pages()

    items = []
    sidebar_items = ws_data.get("sidebar_items") or []
    for item in sorted(sidebar_items, key=lambda i: i.get("idx", 0)):
        item_roles = item.get("roles", "")
        if "System Manager" not in (user.roles or []) and item_roles:
            allowed = {r.strip() for r in item_roles.split(",") if r.strip()}
            if not (allowed & set(user.roles)):
                continue

        item_type = item.get("type", "DocType")
        link_to = item.get("link_to", "")
        item_icon = item.get("icon", "")
        is_singleton = False
        if item_type == "DocType" and link_to:
            dt_meta = await grunt.get_meta(link_to)
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
                # The badge's filters also filter the list the item opens (SidebarItem.vue);
                # count_key matches the key get_counts files that badge's number under.
                "count_filters": item.get("count_filters") or "",
                "count_key": count_key(link_to, parse_count_filters(item)),
                "roles": item_roles,
                "sequence": item.get("idx", 0),
                "is_singleton": is_singleton,
            }
        )

    sections = _sections(ws_data, items)
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
        "dashboards": _dashboards(ws_data, pages),
        "items": items,
        "sections": sections,
        "sidebar_mode": await _sidebar_mode(ws_data, sections),
    }


async def _get_ws_controller(name: str) -> AppMenu:
    # Precisely-typed overloads live on the GruntApp instance (grunt.app.grunt) -
    # the top-level `grunt` package facade's stub can't use `@overload` (mypy
    # requires a real implementation for that in a non-stub .py file), so it
    # falls back to a looser `dict[str, Any] | D` union that doesn't narrow here.

    return await grunt.get_doc(AppMenu, name)


@grunt.whitelist()
async def list_workspaces() -> list[dict[str, Any]]:
    """List workspaces visible to the current user."""
    # Sidebar items across all workspaces touch most of the app's DocTypes.
    # Batch-load them in one query up front instead of letting
    # _workspace_to_dict's per-item grunt.get_meta() lazy-load each one
    # with its own SELECT.
    await doctype_registry.list_all()

    all_ws = await grunt.get_list("AppMenu", fields=["name"], order_by="sequence")
    data = []
    user = grunt.get_user()
    if not user:
        return []
    pages = await _visible_pages()

    for ws_brief in all_ws:
        try:
            ws_data = await grunt.get_doc("AppMenu", ws_brief["name"])
            if ws_data.get("is_hidden") and "System Manager" not in (user.roles or []):
                continue
            # Basic role check could be added here
            data.append(await _workspace_to_dict(ws_data, pages))
        except Exception:
            continue
    return data


@grunt.whitelist()
async def get_workspace(name: str) -> dict[str, Any]:
    """Get a single workspace with filtered items."""
    ws_data = await _get_ws_controller(name)
    return await _workspace_to_dict(ws_data)


@grunt.whitelist(roles=["System Manager"])
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


@grunt.whitelist(roles=["System Manager"])
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


@grunt.whitelist()
async def get_document_stats() -> dict[str, int]:
    """Return an honest, deduplicated document total for the home page.

    Unlike summing per-workspace sidebar counts (which double-counts doctypes
    shared across workspaces and is dominated by log/session churn), this counts
    each business doctype exactly once and excludes infrastructural doctypes
    (logs, sessions, versions, queues, config/metadata).

    Each per-doctype count goes through ``grunt.count(respect_permissions=True)``,
    which is itself cached per (doctype, user, filters) - see its docstring -
    so repeat page loads don't re-run dozens of COUNT queries.
    """
    total = 0
    counted = 0
    for dt in await doctype_registry.list_all():
        if dt.is_child or dt.is_virtual or dt.is_singleton:
            continue
        if not dt.track_activity or dt.hide_from_activity_feed:
            continue
        try:
            total += await grunt.count(dt.name, respect_permissions=True)
            counted += 1
        except Exception:
            # A doctype without a physical table yet - skip it silently.
            continue

    return {"total": total, "doctypes": counted}


@grunt.whitelist()
async def get_my_work() -> dict[str, Any]:
    """Return the current user's personal work items for the home page:

    open tasks assigned to them (flagged when overdue) and unread notifications.
    """
    user = grunt.get_user()
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
            fields=["name", "subject", "ref_doctype", "doc_id", "created_at"],
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
