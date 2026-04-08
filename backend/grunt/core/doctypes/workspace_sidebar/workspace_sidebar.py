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
        counts: dict[str, int] = {}

        async def _get_item_count(item_data: dict[str, Any]) -> tuple[str, int] | None:
            if not item_data.get("show_count") or item_data.get("type") != "DocType":
                return None

            link_to = item_data.get("link_to")
            if not link_to:
                return None

            try:
                dt = await grunt.metadata.get_doctype(link_to)
            except Exception:
                return None

            # Get table name from registry/compiler
            from grunt.core.metadata.compiler import get_table_name  # noqa: PLC0415

            table_name = dt.table_name or get_table_name(dt.module, dt.name)

            try:
                count_sql = f'SELECT COUNT(*) FROM "{table_name}"'  # noqa: S608
                filters = {}
                count_filters_raw = item_data.get("count_filters")
                if count_filters_raw:
                    try:
                        f_data = json.loads(count_filters_raw)
                        if isinstance(f_data, dict) and f_data:
                            filters = f_data
                            conditions = [f'"{col}" = :{col}' for col in filters]
                            count_sql += " WHERE " + " AND ".join(conditions)
                    except (json.JSONDecodeError, ValueError):
                        pass

                result_count = await grunt.db.session.execute(text(count_sql), filters)
                count_val = result_count.scalar() or 0

                # Build key: use link_to + suffix if filters exist
                key = link_to
                if filters:
                    suffix = "_".join(str(v).lower() for v in filters.values())
                    key = f"{link_to}_{suffix}"

                return key, count_val
            except Exception:
                logger.warning("workspace.count_error", link_to=link_to)
                return None

        tasks = [_get_item_count(item) for item in self.get("sidebar_items", [])]
        results = await asyncio.gather(*tasks)
        for res in results:
            if res:
                key, val = res
                counts[key] = val

        return counts

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
