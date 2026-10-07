"""AppMenu DocType controller.

Encapsulates logic for workspace navigation and sidebar counts.
"""

from __future__ import annotations

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
