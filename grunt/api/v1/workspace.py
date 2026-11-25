"""Workspace whitelisted methods."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from typing import Any

from grunt.api.context import whitelist
from grunt.api.v1.dashboard import page_visible
from grunt.apps.manifest import extenders
from grunt.auth.current import acting_user
from grunt.document.base import Document
from grunt.document.titles import resolve_reference_titles
from grunt.errors import forbidden
from grunt.i18n import _
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.permissions.perms import has_perm
from grunt.permissions.query import allowed_doctypes
from grunt.permissions.rbac import permission_checker
from grunt.reports.access import ACCESS_FIELDS, runnable
from grunt.site.doctypes.AppMenu.app_menu import (
    AppMenu,
    count_key,
    order_menu,
    parse_count_filters,
)
from grunt.site.manager import site_manager
from grunt.site.settings import get_setting
from grunt.workflow.inbox import awaiting_actions
lazy from grunt.document.api import documents


async def _visible_pages() -> list[dict[str, Any]]:
    """Pages the current user may open, as dashboard candidates for the apps."""
    user = acting_user()
    pages = await documents.get_list(
        "Page",
        fields=["name", "label", "app", "is_published", "roles"],
        limit=1000,
        include_total=False,
    )
    manager = await has_perm("grunt.manage_desk")
    visible = [p for p in pages if page_visible(p, user.role_names, manager=manager)]
    return sorted(visible, key=lambda p: str(p.get("label") or p["name"]).casefold())


def _dashboards(ws_data: Any, pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The app's dashboards for the switcher on its home: the home page first,
    then the other pages of the same app and of the apps that extend it
    (``extends`` in their manifest), each only if the user may open it."""
    home = ws_data.get("home_page")
    app = ws_data.get("app")
    apps = {app, *_extenders(app)} if app else set()
    picked = [p for p in pages if p["name"] == home]
    picked += [p for p in pages if p.get("app") in apps and p["name"] != home]
    return [{"name": p["name"], "label": p.get("label") or p["name"]} for p in picked]


def _extenders(app: str) -> list[str]:
    site = site_manager.get_active_site()
    installed = tuple(site_manager.get_installed_apps(site)) if site else ()
    return _extenders_of(installed, app)


@cache
def _extenders_of(installed: tuple[str, ...], app: str) -> list[str]:
    # Manifests are read once per process - they change only with a restart anyway.
    return extenders(site_manager.bench_dir / "apps", list(installed), app)


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


@dataclass
class _Visible:
    """What the current user may open from the menus: the sidebar shows only
    those items. A desk manager (``grunt.manage_desk``) sees every item - they
    edit the menus."""

    manager: bool
    roles: frozenset[str]
    pages: list[dict[str, Any]]
    doctypes: set[str] = field(default_factory=set)
    reports: set[str] = field(default_factory=set)
    page_items: set[str] = field(default_factory=set)

    def app(self, ws_data: Any) -> bool:
        """``AppMenu.roles`` - the app is for these roles only (empty: everyone)."""
        return self.manager or _roles_allow(ws_data.get("roles"), self.roles)

    def item(self, item: dict[str, Any]) -> bool:
        if self.manager:
            return True
        if not _roles_allow(item.get("roles"), self.roles):
            return False
        target = item.get("link_to") or ""
        match item.get("type") or "DocType":
            case "DocType":
                return target in self.doctypes
            case "Report":
                return target in self.reports
            case "Page":
                return target in self.page_items
        return True  # URL, Divider


def _roles_allow(roles: str | None, held: Iterable[str]) -> bool:
    allowed = {r.strip() for r in (roles or "").split(",") if r.strip()}
    return not allowed or bool(allowed & set(held))


async def _visible(menus: Iterable[Any]) -> _Visible:
    """:class:`_Visible` for the items of *menus* - the read permissions of all
    their DocTypes and reports decided at once."""
    user = acting_user()
    manager = await has_perm("grunt.manage_desk")
    visible = _Visible(manager, frozenset(user.role_names), await _visible_pages())
    if manager:
        return visible
    # A menu read by its class holds its items as documents: their rows.
    items = [
        i.data if isinstance(i, Document) else i
        for ws in menus
        for i in ws.get("sidebar_items") or []
    ]
    targets = {
        kind: {i["link_to"] for i in items if i.get("type") == kind and i.get("link_to")}
        for kind in ("DocType", "Report", "Page")
    }
    metas = [m for n in sorted(targets["DocType"]) if (m := await doctype_registry.get_meta(n))]
    visible.doctypes = await allowed_doctypes(metas, "read")
    visible.reports = await _visible_reports(targets["Report"])
    visible.page_items = await _visible_page_items(targets["Page"], visible.roles)
    return visible


async def _visible_page_items(names: set[str], roles: frozenset[str]) -> set[str]:
    """Those of the pages *names* (sidebar items) the user may open - looked up
    by name, not out of the capped list of pages the dashboards use."""
    if not names:
        return set()
    pages = await documents.get_list(
        "Page",
        filters={"name__in": sorted(names)},
        fields=["name", "is_published", "roles"],
        limit=len(names),
        include_total=False,
    )
    return {p["name"] for p in pages if page_visible(p, roles)}


async def _visible_reports(names: set[str]) -> set[str]:
    """Those of the reports *names* the user may run
    (:func:`grunt.reports.access.runnable`) - and so open."""
    report_meta = await doctype_registry.get_meta("Report")
    if not names or report_meta is None or not await permission_checker.check(report_meta, "read"):
        return set()
    reports = await documents.get_list(
        "Report",
        filters={"report_name__in": sorted(names)},
        fields=ACCESS_FIELDS,
        limit=len(names),
        include_total=False,
    )
    return {r["report_name"] for r in await runnable(reports, acting_user().email)}


def _drop_stray_dividers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A divider stays only between two items of its section - hidden items
    mustn't leave one at a section's edge or two in a row."""
    out: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if item["type"] != "Divider":
            out.append(item)
            continue
        before = out[-1] if out else None
        after = next((n for n in items[i + 1 :] if n["type"] != "Divider"), None)
        if (
            before is not None
            and before["type"] != "Divider"
            and before["section"] == item["section"]
            and after is not None
            and after["section"] == item["section"]
        ):
            out.append(item)
    return out


async def _workspace_to_dict(ws_data: Any, visible: _Visible) -> dict[str, Any]:
    """Convert AppMenu document data to dict, with only the items the user may open."""

    items = []
    sidebar_items = ws_data.get("sidebar_items") or []
    for position, item in enumerate(order_menu(sidebar_items, ws_data.get("sections") or [])):
        if not visible.item(item):
            continue
        item_roles = item.get("roles", "")
        item_type = item.get("type", "DocType")
        link_to = item.get("link_to", "")
        item_icon = item.get("icon", "")
        is_singleton = False
        if item_type == "DocType" and link_to:
            dt_meta = await doctype_registry.get_meta(link_to)
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
                "sequence": position,
                "is_singleton": is_singleton,
            }
        )

    if not visible.manager:  # the menu editor works on every row as stored
        items = _drop_stray_dividers(items)
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
        "dashboards": _dashboards(ws_data, visible.pages),
        "items": items,
        "sections": sections,
        "sidebar_mode": await _sidebar_mode(ws_data, sections),
    }


async def _get_ws_controller(name: str) -> AppMenu:
    # Precisely-typed overloads live on the GruntApp instance (grunt.app.grunt) -
    # the top-level `grunt` package facade's stub can't use `@overload` (mypy
    # requires a real implementation for that in a non-stub .py file), so it
    # falls back to a looser `dict[str, Any] | D` union that doesn't narrow here.

    return await AppMenu.get_doc(name)


@whitelist()
async def list_workspaces() -> list[dict[str, Any]]:
    """List workspaces visible to the current user."""
    # Sidebar items across all workspaces touch most of the app's DocTypes.
    # Batch-load them in one query up front instead of letting
    # _workspace_to_dict's per-item doctype_registry.get_meta() lazy-load each one
    # with its own SELECT.
    await doctype_registry.list_all()

    all_ws = await documents.get_list("AppMenu", fields=["name"], order_by="sequence")
    if not acting_user():
        return []
    menus = []
    for ws_brief in all_ws:
        try:
            menus.append(await AppMenu.get_doc(ws_brief["name"]))
        except Exception:
            continue
    visible = await _visible(menus)
    data = []
    for ws_data in menus:
        if not visible.manager and (ws_data.is_hidden or not visible.app(ws_data)):
            continue
        try:
            menu = await _workspace_to_dict(ws_data, visible)
        except Exception:
            continue
        if visible.manager or _has_content(menu):
            data.append(menu)
    return data


def _has_content(menu: dict[str, Any]) -> bool:
    """An app is shown when the user may open something in it: an item that
    isn't a divider, or a dashboard."""
    return bool(menu["dashboards"]) or any(i["type"] != "Divider" for i in menu["items"])


@whitelist()
async def get_workspace(name: str) -> dict[str, Any]:
    """Get a single workspace with filtered items - ``403`` for an app the
    user may not open (see :func:`list_workspaces`)."""
    ws_data = await _get_ws_controller(name)
    visible = await _visible([ws_data])
    menu = await _workspace_to_dict(ws_data, visible) if visible.app(ws_data) else None
    if menu is None or not (visible.manager or _has_content(menu)):
        raise forbidden(_("No access to the app “%(app)s”") % {"app": _(ws_data.label or name)})
    return menu


@whitelist(perm="grunt.manage_desk")
async def save_workspace(workspace_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a workspace. Admin only."""
    data = workspace_data.copy()
    if "items" in data:
        data["sidebar_items"] = data.pop("items")

    name = data.get("name")
    if name:
        ws_data = await documents.save_doc("AppMenu", name, data)
    else:
        ws_data = await documents.new_doc("AppMenu", data)

    return await _workspace_to_dict(ws_data, await _visible([ws_data]))


@whitelist(perm="grunt.manage_desk")
async def delete_workspace(name: str) -> bool:
    """Delete a workspace. Admin only."""
    await documents.delete_doc("AppMenu", name)
    return True


@whitelist()
async def get_counts(name: str) -> dict[str, int]:
    """Get document counts for workspace links."""
    ws = await _get_ws_controller(name)
    visible = await _visible([ws])
    if not visible.app(ws):
        return {}
    return await ws.get_counts(visible=visible.item)


@whitelist()
async def get_document_stats() -> dict[str, int]:
    """Return an honest, deduplicated document total for the home page.

    Unlike summing per-workspace sidebar counts (which double-counts doctypes
    shared across workspaces and is dominated by log/session churn), this counts
    each business doctype exactly once and excludes infrastructural doctypes
    (logs, sessions, versions, queues, config/metadata).

    Each per-doctype count goes through ``documents.count(respect_permissions=True)``,
    which is itself cached per (doctype, user, filters) - see its docstring -
    so repeat page loads don't re-run dozens of COUNT queries.
    """
    total = 0
    counted = 0
    for dt in await doctype_registry.list_all():
        if dt.is_child or not dt.has_table or dt.is_singleton:
            continue
        if not dt.track_activity or dt.hide_from_activity_feed:
            continue
        try:
            total += await documents.count(dt.name, respect_permissions=True)
            counted += 1
        except Exception:
            # A doctype without a physical table yet - skip it silently.
            continue

    return {"total": total, "doctypes": counted}


@whitelist()
async def get_my_work() -> dict[str, Any]:
    """Return the current user's personal work items for the home page:

    open tasks assigned to them (flagged when overdue), unread notifications and
    workflow documents awaiting their action.
    """
    user = acting_user()
    email = user.email
    today = date.today().isoformat()

    # Open tasks assigned to me.
    try:
        todos = await documents.get_list(
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
        notifications = await documents.get_list(
            "NotificationLog",
            filters={"user": email, "is_read": False},
            fields=["name", "subject", "ref_doctype", "doc_id", "created_at"],
            order_by="created_at",
            order="desc",
            limit=20,
        )
    except Exception:
        notifications = []

    # Workflow documents I can move on now (grunt.workflow.inbox).
    try:
        awaiting = await awaiting_actions(email)
    except Exception:
        log.exception("my_work.awaiting_failed")
        awaiting = []

    return {
        "assigned": assigned,
        "notifications": notifications,
        "awaiting": awaiting,
        "counts": {
            "assigned": len(assigned),
            "overdue": overdue,
            "unread": len(notifications),
            "awaiting": len(awaiting),
        },
    }
