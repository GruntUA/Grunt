"""Dashboard whitelisted methods for widget computation."""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

import grunt

logger = structlog.get_logger()

_TIMESPAN_DAYS = {
    "last_week": 7,
    "last_month": 30,
    "last_quarter": 90,
    "last_year": 365,
    "all_time": 0,
    # Short aliases
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "365d": 365,
}


def _widget_filters(widget: Any) -> dict[str, Any]:
    """Return the widget's static filters as a dict.

    The ``filters`` field is declared as JSON, so it may arrive either already
    decoded (dict) or as a raw JSON string depending on the storage backend.
    Anything unparseable is treated as "no filters" rather than failing the
    whole widget.
    """
    raw = widget.get("filters")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except TypeError, ValueError:
            logger.warning("dashboard.bad_filters", filters=raw)
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


async def _compute_widget_data(
    widget: Any,
    global_since: datetime | None = None,
    global_until: datetime | None = None,
) -> Any:
    """Compute data for a single widget row."""
    from grunt.metadata.registry import doctype_registry

    doctype_name: str = widget.get("doctype") or ""
    if not doctype_name:
        return None

    try:
        dt = await doctype_registry.get(doctype_name)
    except Exception:
        logger.warning("dashboard.unknown_doctype", doctype=doctype_name)
        return None

    period_key = widget.get("period") or "last_month"
    days = _TIMESPAN_DAYS.get(period_key, 30)
    now = datetime.now(UTC)
    since = global_since if global_since is not None else now - timedelta(days=days)
    until = global_until if global_until is not None else now
    widget_type: str = widget.get("widget_type") or "metric"
    base_filters = _widget_filters(widget)

    if widget_type in ("metric", "gauge"):
        agg = widget.get("aggregation") or "count"
        field = widget.get("field") or "*"
        date_field = widget.get("date_field")
        filters = dict(base_filters)
        prev_filters = dict(base_filters)
        if date_field:
            filters[f"{date_field}__gte"] = since.isoformat()
            prev_filters[f"{date_field}__gte"] = (since - timedelta(days=days)).isoformat()
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
            return {"value": 0, "trend": None}

    if widget_type in ("chart_area", "chart_bar"):
        date_field = widget.get("date_field")
        if not date_field:
            return {"labels": [], "values": []}
        group_by = widget.get("group_by") or ""
        date_expr = f"date({date_field})"
        try:
            filters = {
                **base_filters,
                f"{date_field}__gte": since.isoformat(),
                f"{date_field}__lte": until.isoformat(),
            }
            if group_by:
                rows = await grunt.db.aggregate(
                    doctype_name,
                    filters=filters,
                    group_by=[date_expr, group_by],
                    aggregations={"cnt": "count"},
                    order_by=date_expr,
                    order="asc",
                )
                # collect all labels (dates) and all group values
                all_labels: list[str] = sorted({str(r.get(date_expr)) for r in rows})
                group_values: list[str] = sorted(
                    {str(r.get(group_by)) for r in rows if r.get(group_by) is not None}
                )
                # build lookup: (date, group) -> count
                lookup: dict[tuple[str, str], int] = {
                    (str(r.get(date_expr)), str(r.get(group_by))): int(r.get("cnt") or 0)
                    for r in rows
                }
                groups = {
                    gv: [lookup.get((lbl, gv), 0) for lbl in all_labels] for gv in group_values
                }
                return {"labels": all_labels, "groups": groups}
            else:
                rows = await grunt.db.aggregate(
                    doctype_name,
                    filters=filters,
                    group_by=date_expr,
                    aggregations={"cnt": "count"},
                    order_by=date_expr,
                    order="asc",
                )
                return {
                    "labels": [str(r.get(date_expr)) for r in rows],
                    "values": [r.get("cnt") for r in rows],
                }
        except Exception:
            return {"labels": [], "values": []}

    if widget_type == "donut":
        group_by = widget.get("group_by")
        if not group_by:
            return {"labels": [], "values": []}
        try:
            rows = await grunt.db.aggregate(
                doctype_name,
                filters=base_filters or None,
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
            return {"labels": [], "values": []}

    if widget_type == "list":
        try:
            items = await grunt.get_list(
                doctype_name,
                filters=base_filters or None,
                order_by="modified_at",
                order="desc",
                limit=8,
            )
            return {"items": items, "title_field": dt.title_field}
        except Exception:
            return {"items": [], "title_field": None}

    if widget_type == "shortcut":
        try:
            if dt.is_singleton:
                return {"count": 1}
            return {"count": await grunt.count(doctype_name, filters=base_filters or None)}
        except Exception:
            return None

    if widget_type == "calendar":
        date_field = widget.get("date_field")
        if not date_field:
            return {"days": {}}
        try:
            group_by_expr = f"date({date_field})"
            filters = {
                **base_filters,
                f"{date_field}__gte": since.isoformat(),
                f"{date_field}__lte": until.isoformat(),
            }
            rows = await grunt.db.aggregate(
                doctype_name, filters=filters, group_by=group_by_expr, aggregations={"cnt": "count"}
            )
            return {"days": {str(r.get(group_by_expr)): r.get("cnt") for r in rows}}
        except Exception:
            return {"days": {}}

    if widget_type == "heatmap":
        date_field = widget.get("date_field")
        if not date_field:
            return {"entries": []}
        try:
            group_by_expr = f"date({date_field})"
            filters = {**base_filters, f"{date_field}__gte": since.isoformat()}
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
            filters = dict(base_filters)
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
            return {"stages": []}

    if widget_type == "table":
        group_by = widget.get("group_by")
        if not group_by:
            return {"rows": []}
        try:
            agg = widget.get("aggregation") or "count"
            value_field = widget.get("field")
            agg_expr = f"{agg}({value_field})" if agg != "count" and value_field else "count"
            filters = dict(base_filters)
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
            return {
                "rows": [
                    {
                        "label": str(r.get(group_by)) if r.get(group_by) is not None else "—",
                        "value": round(float(r.get("value") or 0), 2),
                    }
                    for r in rows
                ],
                "aggregation": agg,
                "field": value_field,
            }
        except Exception:
            return {"rows": []}

    if widget_type == "activity":
        try:
            filters = dict(base_filters)
            if doctype_name:
                filters["doctype"] = doctype_name
            items = await grunt.get_list(
                "ActivityLog", filters=filters, order_by="created_at", order="desc", limit=20
            )
            return {"items": items}
        except Exception:
            return {"items": []}

    return None


@grunt.whitelist()
async def get_page_data(
    name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Return computed data for all widgets of a Page document."""
    from grunt.app import grunt as grunt_app

    try:
        dashboard = dict(await grunt.get_doc("Page", name))
    except Exception:
        grunt.throw("Сторінку не знайдено", "NOT_FOUND")

    user = grunt_app._require_user()
    if not user.is_superadmin and not dashboard.get("is_published"):
        grunt.throw("Сторінку не опубліковано", "PERMISSION_DENIED")

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
        except Exception:
            result = None
        return w_dict["name"], result

    pairs = await asyncio.gather(*(_safe_compute(w) for w in widgets))
    return dict(pairs)


@grunt.whitelist()
async def get_dashboard_data(
    name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Return computed data for all widgets of a Dashboard document."""
    from grunt.app import grunt as grunt_app

    try:
        dashboard = dict(await grunt.get_doc("Dashboard", name))
    except Exception:
        grunt.throw("Дашборд не знайдено", "NOT_FOUND")

    user = grunt_app._require_user()
    if not user.is_superadmin and not dashboard.get("is_published"):
        grunt.throw("Дашборд не опубліковано", "PERMISSION_DENIED")

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
        except Exception:
            result = None
        return w_dict["name"], result

    pairs = await asyncio.gather(*(_safe_compute(w) for w in widgets))
    return dict(pairs)
