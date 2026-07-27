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


# Cached because the stat costs one COUNT per business doctype (dozens of
# queries) while being a purely informational figure on the home page.
_DOC_STATS_TTL_SECONDS = 60.0
_doc_stats_cache: dict[str, tuple[float, dict[str, int]]] = {}


@grunt.whitelist()
async def get_document_stats() -> dict[str, int]:
    """Return an honest, deduplicated document total for the home page.

    Unlike summing per-workspace sidebar counts (which double-counts doctypes
    shared across workspaces and is dominated by log/session churn), this counts
    each business doctype exactly once and excludes infrastructural doctypes
    (logs, sessions, versions, queues, config/metadata).

    Result is cached per site for a minute — an approximate headline number is
    not worth dozens of COUNT queries on every page load.
    """
    import time

    from grunt.activity import FEED_HIDDEN_DOCTYPES
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager

    try:
        site = site_manager.get_active_site()
    except Exception:
        site = ""

    now = time.monotonic()
    cached = _doc_stats_cache.get(site)
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
            total += await grunt.count(dt.name)
            counted += 1
        except Exception:
            # A doctype without a physical table yet — skip it silently.
            continue

    stats = {"total": total, "doctypes": counted}
    _doc_stats_cache[site] = (now, stats)
    return stats


async def _resolve_ref_titles(
    refs: list[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    """Resolve (doctype, id) references to display titles, one query per doctype."""
    from grunt.metadata.registry import doctype_registry

    by_doctype: dict[str, set[str]] = {}
    for dt_name, doc_id in refs:
        if dt_name and doc_id:
            by_doctype.setdefault(dt_name, set()).add(doc_id)

    titles: dict[tuple[str, str], str] = {}
    for dt_name, ids in by_doctype.items():
        try:
            dt = await doctype_registry.get(dt_name)
        except Exception:
            continue
        title_field = dt.title_field
        if not title_field or title_field == "name":
            continue
        try:
            rows = await grunt.get_list(
                dt_name,
                filters={"name__in": list(ids)},
                fields=["name", title_field],
                limit=len(ids),
            )
        except Exception:
            continue
        for r in rows:
            if r.get(title_field):
                titles[(dt_name, r["name"])] = r[title_field]
    return titles


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

    titles = await _resolve_ref_titles(
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
