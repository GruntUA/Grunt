"""AppMenu DocType controller.

Encapsulates logic for workspace navigation and sidebar counts.
"""

import hashlib
import json
from typing import Any

import grunt
from grunt import log
from grunt.document.base import Document


def parse_count_filters(item: dict[str, Any]) -> dict[str, Any]:
    """A sidebar item's ``count_filters`` JSON -> filters dict (``{}`` when unset/invalid)."""
    raw = item.get("count_filters")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError, ValueError:
        return {}


def count_key(doctype: str, filters: dict[str, Any]) -> str:
    """Key of a sidebar item's count in get_counts' result (unique per filters)."""
    if not filters:
        return doctype
    suffix = "_".join(str(v).lower() for v in filters.values())
    return f"{doctype}_{suffix}"


def order_menu(items: list[dict[str, Any]], sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sidebar rows in display order.

    The menu's own rows keep their ``idx`` order. Rows other apps contributed
    (``source_app`` set) are then placed one by one, per app in their own order:

    * ``anchor_after``/``anchor_before`` - next to the item with that ``link_to`` or label;
    * else at the end of their section, when it is already in the menu;
    * else, for a new section, after/before the section its WorkspaceSection row
      anchors to;
    * else at the end of the menu.

    Rows aren't renumbered in the DB: the base app's sync rewrites its own rows
    on every ``migrate``, so positions computed then would go stale.
    """

    def idx(row: dict[str, Any]) -> int:
        return row.get("idx") or 0

    own = sorted((r for r in items if not r.get("source_app")), key=idx)
    contributed = sorted(
        (r for r in items if r.get("source_app")), key=lambda r: (r["source_app"], idx(r))
    )
    section_anchors = {
        s.get("section"): (s.get("anchor_after") or "", s.get("anchor_before") or "")
        for s in sections
        if s.get("source_app")
    }
    result = list(own)

    def place(ref: str, *, after: bool, in_section: bool = False) -> int | None:
        """Index next to the rows matching *ref* (a section, or an item's link/label)."""
        hits = [
            i
            for i, r in enumerate(result)
            if ref
            and (
                r.get("section") == ref if in_section else ref in (r.get("link_to"), r.get("label"))
            )
        ]
        if not hits:
            return None
        return hits[-1] + 1 if after else hits[0]

    for row in contributed:
        after, before = row.get("anchor_after") or "", row.get("anchor_before") or ""
        section = row.get("section") or ""
        at = place(after or before, after=bool(after))
        if at is None and section:
            at = place(section, after=True, in_section=True)
        if at is None and section in section_anchors:
            s_after, s_before = section_anchors[section]
            at = place(s_after or s_before, after=bool(s_after), in_section=True)
        result.insert(len(result) if at is None else at, row)
    return result


# Tailwind 600 shades: distinct from one another and readable under a white icon.
_PALETTE = (
    "#DC2626", "#EA580C", "#D97706", "#CA8A04", "#65A30D", "#16A34A",
    "#059669", "#0D9488", "#0891B2", "#0284C7", "#2563EB", "#4F46E5",
    "#7C3AED", "#9333EA", "#C026D3", "#DB2777", "#E11D48",
)  # fmt: skip


def default_color(name: str) -> str:
    """Accent colour picked from the palette by a hash of the workspace name,
    so it stays the same across restarts and sites."""
    return _PALETTE[int(hashlib.blake2b(name.encode()).hexdigest(), 16) % len(_PALETTE)]


class AppMenu(Document):
    """Controller for AppMenu DocType."""

    label: str
    icon: str
    color: str
    description: str
    sequence: int
    is_hidden: bool
    roles: str
    app: str
    home_page: str
    sidebar_items: list[dict[str, Any]]

    # Maps sidebar item type -> doctype name used by DynamicLink for search.
    # Empty string means no link picker (DynamicLink falls back to plain text).
    _LINK_DOCTYPE: dict[str, str] = {
        "DocType": "DocType",
        "Report": "Report",
        "Page": "Page",
    }

    async def validate(self) -> None:
        if not self.color:
            self.color = default_color(self.name or self.label or "")

    async def on_load(self) -> None:
        for item in self.get("sidebar_items", []):
            item["link_doctype"] = self._LINK_DOCTYPE.get(item.get("type", ""), "")

    async def get_counts(self) -> dict[str, int]:
        """Get document counts for sidebar items that have show_count=true.

        Counts go through ``grunt.count``, so each badge reflects only the
        rows the current user may actually see (same row-level permission
        filter the list view applies) - never a raw table total.
        """
        items = [
            item
            for item in self.get("sidebar_items", [])
            if item.get("show_count") and item.get("type") == "DocType" and item.get("link_to")
        ]
        if not items:
            return {}

        counts: dict[str, int] = {}
        for item in items:
            link_to = item["link_to"]
            dt = await grunt.get_meta(link_to)
            if dt is None:
                continue

            filters = self._parse_filters(item)
            key = self._generate_count_key(link_to, filters)

            try:
                counts[key] = await grunt.count(
                    link_to, filters=filters or None, respect_permissions=True
                )
            except Exception as e:  # table not built yet, source unreachable
                log.warning("workspace.count_error", doctype=link_to, error=str(e))

        return counts

    def _parse_filters(self, item: dict[str, Any]) -> dict[str, Any]:
        return parse_count_filters(item)

    def _generate_count_key(self, doctype: str, filters: dict[str, Any]) -> str:
        return count_key(doctype, filters)

    def has_access(self, user: Any) -> bool:
        """Check if user has access to this workspace based on roles."""
        if "System Manager" in (getattr(user, "roles", None) or []):
            return True
        if not self.roles:
            return True
        allowed = {r.strip() for r in self.roles.split(",") if r.strip()}
        return bool(allowed & set(user.roles))
