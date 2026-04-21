"""WorkspaceSidebar DocType controller.

Encapsulates logic for workspace navigation, sidebar counts, and dashboard widgets.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import text

from grunt.app import grunt
from grunt.core.document.base import Document

if TYPE_CHECKING:
    from datetime import datetime

logger = structlog.get_logger()


class WorkspaceSidebar(Document):
    """Controller for WorkspaceSidebar DocType."""

    label: str
    icon: str
    color: str
    description: str
    sequence: int
    is_hidden: bool
    roles: str
    app: str
    sidebar_items: list[dict[str, Any]]
    widgets: str  # JSON string in DB

    async def get_counts(self) -> dict[str, int]:
        """Get document counts for sidebar items that have show_count=true."""
        from grunt.core.metadata.compiler import get_table_name  # noqa: PLC0415

        items = [
            item for item in self.get("sidebar_items", [])
            if item.get("show_count") and item.get("type") == "DocType" and item.get("link_to")
        ]
        if not items:
            return {}

        # Resolve table names via in-memory meta cache (no extra queries)
        resolved: list[tuple[str, str, dict[str, Any]]] = []
        for item in items:
            link_to = item["link_to"]
            try:
                dt = await grunt.get_meta(link_to)
            except Exception:
                continue
            table_name = dt.table_name or get_table_name(dt.module, dt.name)

            filters: dict[str, Any] = {}
            count_filters_raw = item.get("count_filters")
            if count_filters_raw:
                try:
                    f_data = json.loads(count_filters_raw)
                    if isinstance(f_data, dict) and f_data:
                        filters = f_data
                except (json.JSONDecodeError, ValueError):
                    pass

            key = link_to
            if filters:
                suffix = "_".join(str(v).lower() for v in filters.values())
                key = f"{link_to}_{suffix}"

            resolved.append((key, table_name, filters))

        if not resolved:
            return {}

        # Single UNION ALL instead of N separate COUNT queries
        parts: list[str] = []
        params: dict[str, Any] = {}
        for i, (key, table_name, filters) in enumerate(resolved):
            key_param = f"k{i}"
            params[key_param] = key
            if filters:
                conditions = []
                for col, val in filters.items():
                    p = f"{col}_{i}"
                    params[p] = val
                    conditions.append(f'"{col}" = :{p}')
                where = " WHERE " + " AND ".join(conditions)
            else:
                where = ""
            parts.append(f'SELECT :{key_param} AS k, COUNT(*) AS c FROM "{table_name}"{where}')  # noqa: S608

        try:
            result = await grunt.db._session().execute(text(" UNION ALL ".join(parts)), params)
            return {row.k: row.c for row in result}
        except Exception:
            logger.warning("workspace.counts_error")
            return {}

    async def get_widget_data(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute widget data for all widgets in the workspace."""
        from grunt.api.v1.dashboard import _compute_widget_data  # noqa: PLC0415

        widgets_raw = self.get("widgets")
        widgets: list[dict[str, Any]] = sorted(
            json.loads(widgets_raw) if widgets_raw else [],
            key=lambda w: w.get("sequence") or 0,
        )

        async def _safe_compute(w: dict[str, Any]) -> tuple[str, Any]:
            try:
                result = await _compute_widget_data(w, global_since=date_from, global_until=date_to)
            except Exception as e:
                logger.warning("workspace.widget_data_error", widget_id=w.get("id"), error=str(e))
                result = None
            return w["id"], result

        tasks = [_safe_compute(w) for w in widgets if w.get("id")]
        pairs = await asyncio.gather(*tasks)
        return dict(pairs)

    def has_access(self, user: Any) -> bool:
        """Check if user has access to this workspace based on roles."""
        if user.is_superadmin:
            return True
        if not self.roles:
            return True
        allowed = {r.strip() for r in self.roles.split(",") if r.strip()}
        return bool(allowed & set(user.roles))
