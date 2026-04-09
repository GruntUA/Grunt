"""Dashboard API — widget data computation.

CRUD for Dashboard documents is handled by the standard /api/v1/docs/Dashboard/
endpoint.  This module provides only the data computation endpoint that runs
aggregation queries for each widget.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import HTTPException, Query

from grunt.api.router import GruntRouter
from grunt.app import grunt
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

router = GruntRouter(prefix="", tags=["dashboard"])

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}

# Human-readable timespan → days mapping (0 = no date filter)
_TIMESPAN_DAYS: dict[str, int] = {
    "last_week": 7,
    "last_month": 30,
    "last_quarter": 90,
    "last_year": 365,
    "all_time": 0,
}

# Supported aggregation functions (name → SQLAlchemy func)

from sqlalchemy import func as _sa_func  # noqa: E402

_AGGREGATION_FNS: dict[str, Any] = {
    "count": _sa_func.count,
    "sum": _sa_func.sum,
    "avg": _sa_func.avg,
    "min": _sa_func.min,
    "max": _sa_func.max,
}


# ── Widget data computation ────────────────────────────────────────────────


async def _compute_widget_data(
    widget: Any,
    global_since: datetime | None = None,
    global_until: datetime | None = None,
) -> Any:
    """Compute data for a single widget row."""
    doctype_name: str = widget.get("doctype") or ""
    if not doctype_name:
        return None

    try:
        dt = await doctype_registry.get(doctype_name)
    except Exception:
        logger.warning("dashboard.unknown_doctype", doctype=doctype_name)
        return None

    period_days = _PERIOD_DAYS.get(widget.get("period") or "30d", 30)
    now = datetime.now(UTC)
    # Global date filter overrides per-widget period
    since = global_since if global_since is not None else now - timedelta(days=period_days)
    until = global_until if global_until is not None else now
    widget_type: str = widget.get("widget_type") or "metric"

    if widget_type == "metric":
        agg = widget.get("aggregation") or "count"
        field = widget.get("field") or "*"

        date_field = widget.get("date_field")
        filters = {}
        prev_filters = {}
        if date_field:
            filters[f"{date_field}__gte"] = since.isoformat()
            prev_filters[f"{date_field}__gte"] = (since - timedelta(days=period_days)).isoformat()
            prev_filters[f"{date_field}__lt"] = since.isoformat()

        agg_expr = f"{agg}({field})" if agg != "count" else "count"

        try:
            curr_data = await grunt.db.aggregate(
                doctype_name, filters=filters if filters else None, aggregations={"val": agg_expr}
            )
            val = curr_data[0].get("val") or 0

            if date_field:
                prev_data = await grunt.db.aggregate(
                    doctype_name, filters=prev_filters, aggregations={"val": agg_expr}
                )
                prev_val = prev_data[0].get("val") or 0
                trend = round((val - prev_val) / prev_val * 100, 1) if prev_val else None
            else:
                trend = None

            return {"value": val, "trend": trend}
        except Exception:
            logger.exception("dashboard.metric_error", doctype=doctype_name)
            return {"value": 0, "trend": None}

    if widget_type in ("chart_area", "chart_bar"):
        date_field = widget.get("date_field")
        if not date_field:
            return {"labels": [], "values": []}

        try:
            filters = {
                f"{date_field}__gte": since.isoformat(),
                f"{date_field}__lte": until.isoformat(),
            }
            group_by_expr = f"date({date_field})"

            rows = await grunt.db.aggregate(
                doctype_name,
                filters=filters,
                group_by=group_by_expr,
                aggregations={"cnt": "count"},
                order_by=group_by_expr,
                order="asc",
            )
            return {
                "labels": [str(r.get(group_by_expr)) for r in rows],
                "values": [r.get("cnt") for r in rows],
            }
        except Exception:
            logger.exception("dashboard.chart_error", widget_type=widget_type, doctype=doctype_name)
            return {"labels": [], "values": []}

    if widget_type == "donut":
        group_by = widget.get("group_by")
        if not group_by:
            return {"labels": [], "values": []}
        try:
            rows = await grunt.db.aggregate(
                doctype_name,
                group_by=group_by,
                aggregations={"cnt": "count"},
                order_by="cnt",
                order="desc",
                limit=8,
            )
            return {
                "labels": [str(r.get(group_by)) for r in rows],
                "values": [r.get("cnt") for r in rows],
            }
        except Exception:
            logger.exception("dashboard.donut_error", doctype=doctype_name)
            return {"labels": [], "values": []}

    if widget_type == "list":
        try:
            # We assume grunt.get_list sorts using descending modified_at by default
            items = await grunt.get_list(
                doctype_name, order_by="modified_at", order="desc", limit=8
            )
            return {"items": items, "title_field": dt.title_field}
        except Exception:
            logger.exception("dashboard.list_error", doctype=doctype_name)
            return {"items": [], "title_field": None}

    if widget_type == "shortcut":
        try:
            # Singleton DocTypes always have exactly one record — skip the DB count
            if dt.is_singleton:
                return {"count": 1}
            count = await grunt.count(doctype_name)
            return {"count": count}
        except Exception:
            logger.warning("dashboard.shortcut_unknown_doctype", doctype=doctype_name)
            return None

    if widget_type == "shortcuts_grid":
        return None

    if widget_type == "calendar":
        date_field = widget.get("date_field")
        if not date_field:
            return {"days": {}}
        try:
            group_by_expr = f"date({date_field})"
            filters = {
                f"{date_field}__gte": since.isoformat(),
                f"{date_field}__lte": until.isoformat(),
            }
            rows = await grunt.db.aggregate(
                doctype_name, filters=filters, group_by=group_by_expr, aggregations={"cnt": "count"}
            )
            return {"days": {str(r.get(group_by_expr)): r.get("cnt") for r in rows}}
        except Exception:
            logger.exception("dashboard.calendar_error", doctype=doctype_name)
            return {"days": {}}

    if widget_type == "heatmap":
        date_field = widget.get("date_field")
        if not date_field:
            return {"entries": []}

        try:
            group_by_expr = f"date({date_field})"
            filters = {f"{date_field}__gte": since.isoformat()}

            rows = await grunt.db.aggregate(
                doctype_name,
                filters=filters,
                group_by=group_by_expr,
                aggregations={"cnt": "count"},
                order_by=group_by_expr,
                order="asc",
            )
            return {
                "entries": [
                    {"date": str(r.get(group_by_expr)), "count": r.get("cnt")} for r in rows
                ]
            }
        except Exception:
            logger.exception("dashboard.heatmap_error", doctype=doctype_name)
            return {"entries": []}

    if widget_type == "funnel":
        group_by = widget.get("group_by")
        if not group_by:
            return {"stages": []}
        try:
            field_def = next((f for f in dt.fields if f.fieldname == group_by), None)
            ordered_options = []
            if field_def and field_def.options:
                ordered_options = [o for o in field_def.options.split("\n") if o.strip()]

            filters = {}
            date_field = widget.get("date_field")
            if date_field:
                filters[f"{date_field}__gte"] = since.isoformat()

            rows = await grunt.db.aggregate(
                doctype_name,
                filters=filters if filters else None,
                group_by=group_by,
                aggregations={"cnt": "count"},
            )
            counts = {str(r.get(group_by)): r.get("cnt") for r in rows}

            if ordered_options:
                stages = [{"label": o, "count": counts.get(o, 0)} for o in ordered_options]
            else:
                stages = [
                    {"label": k, "count": v}
                    for k, v in sorted(counts.items(), key=lambda x: -(x[1] or 0))
                ]

            return {"stages": stages}
        except Exception:
            logger.exception("dashboard.funnel_error", doctype=doctype_name)
            return {"stages": []}

    if widget_type == "table":
        group_by = widget.get("group_by")
        if not group_by:
            return {"rows": []}
        try:
            agg = widget.get("aggregation") or "count"
            value_field = widget.get("field")

            agg_expr = f"{agg}({value_field})" if agg != "count" and value_field else "count"

            filters = {}
            date_field = widget.get("date_field")
            if date_field:
                filters[f"{date_field}__gte"] = since.isoformat()
                filters[f"{date_field}__lte"] = until.isoformat()

            rows = await grunt.db.aggregate(
                doctype_name,
                filters=filters if filters else None,
                group_by=group_by,
                aggregations={"value": agg_expr},
                order_by="value",
                order="desc",
                limit=20,
            )

            res_rows = [
                {
                    "label": str(r.get(group_by)) if r.get(group_by) is not None else "—",
                    "value": round(float(r.get("value") or 0), 2),
                }
                for r in rows
            ]
            return {"rows": res_rows, "aggregation": agg, "field": value_field}
        except Exception:
            logger.exception("dashboard.table_error", doctype=doctype_name)
            return {"rows": []}

    if widget_type == "activity":
        try:
            filters = {"doctype": doctype_name} if doctype_name else {}
            items = await grunt.get_list(
                "ActivityLog", filters=filters, order_by="created_at", order="desc", limit=20
            )
            return {"items": items}
        except Exception:
            logger.exception("dashboard.activity_error", doctype=doctype_name)
            return {"items": []}

    return None


@router.get("/dashboard-data/{name}")
async def get_dashboard_data(
    name: str,
    date_from: str | None = Query(None, description="Global date filter from (ISO date)"),
    date_to: str | None = Query(None, description="Global date filter to (ISO date)"),
) -> dict[str, Any]:
    """Return computed data for all widgets of a Dashboard document."""
    try:
        dashboard = dict(await grunt.get_doc("Dashboard", name))
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Дашборд не знайдено") from exc
        raise
    except Exception as err:
        raise HTTPException(status_code=503, detail="Помилка завантаження Дашборду") from err

    user = grunt._require_user()
    if not user.is_superadmin and not dashboard.get("is_published"):
        raise HTTPException(status_code=403, detail="Дашборд не опубліковано")

    # Widgets are already loaded as a child table by get_doc — no extra query needed
    widgets: list[dict[str, Any]] = sorted(
        dashboard.get("widgets") or [],
        key=lambda w: w.get("sequence") or 0,
    )

    global_since: datetime | None = None
    global_until: datetime | None = None
    if date_from:
        with contextlib.suppress(ValueError):
            global_since = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
    if date_to:
        with contextlib.suppress(ValueError):
            global_until = datetime.fromisoformat(date_to).replace(tzinfo=UTC)

    async def _safe_compute(w_dict: dict[str, Any]) -> tuple[str, Any]:
        try:
            result = await _compute_widget_data(
                w_dict, global_since=global_since, global_until=global_until
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("dashboard.widget_data_error", widget_id=w_dict.get("id"), error=str(e))
            result = None
        return w_dict["id"], result

    pairs = await asyncio.gather(*(_safe_compute(w) for w in widgets))
    return {"success": True, "data": dict(pairs)}
