"""Per-widget-type data computation for Dashboard/Page widgets.

Each function here backs one `WidgetType.compute()` (see the `<Type>.py`
files under `frontend/src/components/dashboard/widgets/`) — kept in one
importable module, rather than duplicated across those dynamically-loaded
plugin files, since several widget types share a computation (gauge reuses
`_widget_metric`, chart_bar reuses `_widget_chart`).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from grunt.app import grunt
from grunt.log import log


def _log_widget_failed(doctype_name: str, widget_type: str) -> None:
    log.warning(
        "dashboard.widget_failed",
        doctype=doctype_name,
        widget_type=widget_type,
        exc_info=True,
    )


def _bound(dt: Any, date_field: str, when: datetime, *, upper: bool = False) -> str:
    """A date-range bound for ``date_field`` in the form its list filter input edits.

    Date → ``YYYY-MM-DD`` (the query only compares the date part anyway),
    Datetime → ``YYYY-MM-DDTHH:MM`` — so a widget's drill-down filters show up
    in the list's filter bar instead of an unparseable ISO timestamp. An
    ``upper`` bound rounds up to the minute, so rows from the current minute
    stay in range.
    """
    from grunt.document.meta import Meta

    field = Meta(dt).get_field(date_field) if dt is not None else None
    if field is not None and field.fieldtype == "Date":
        return when.date().isoformat()
    if upper and (when.second or when.microsecond):
        when += timedelta(minutes=1)
    return when.strftime("%Y-%m-%dT%H:%M")


def _as_number(value: Any) -> float:
    """Best-effort numeric coercion for report cell values."""
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except TypeError, ValueError:
        return 0.0


async def _widget_report_series(widget: Any) -> Any:
    """Chart data sourced from a saved Report instead of a doctype aggregate.

    Runs the report and reshapes its rows into the ``{labels, values}`` /
    ``{labels, groups}`` payload the chart/donut renderers already consume,
    using the report's own ``chart_config`` (``label_field`` / ``value_fields``)
    or, absent that, the first column as labels and the second as values.
    """
    from grunt.reports.engine import report_engine

    report_name = widget.get("report") or ""
    try:
        user = grunt._require_user()
        session = grunt._require_session()

        cfg_rows = await grunt.get_list(
            "Report", filters={"report_name": report_name}, fields=["chart_config"], limit=1
        )
        cfg = cfg_rows[0].get("chart_config") if cfg_rows else None
        if isinstance(cfg, str):
            cfg = json.loads(cfg or "{}")
        cfg = cfg or {}

        result = await report_engine.run(report_name, {}, user, session)
        rows = result.get("data") or []
        col_names = [c["fieldname"] for c in result.get("columns") or []]

        label_field = cfg.get("label_field") or (col_names[0] if col_names else None)
        value_fields = list(cfg.get("value_fields") or [])
        if not value_fields:
            value_fields = [c for c in col_names if c != label_field][:1]
        if not label_field or not value_fields:
            return {"labels": [], "values": []}

        labels = [str(r.get(label_field, "—")) for r in rows]
        if len(value_fields) > 1:
            groups = {vf: [_as_number(r.get(vf)) for r in rows] for vf in value_fields}
            return {"labels": labels, "groups": groups}
        return {"labels": labels, "values": [_as_number(r.get(value_fields[0])) for r in rows]}
    except Exception:
        _log_widget_failed(report_name, "report_chart")
        return {"labels": [], "values": []}


async def _widget_metric(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """metric/gauge — a single aggregated value, optionally with a trend vs the prior period."""
    agg = widget.get("aggregation") or "count"
    field = widget.get("field") or "*"
    date_field = widget.get("date_field")
    filters = dict(base_filters)
    prev_filters = dict(base_filters)
    if date_field:
        filters[f"{date_field}__gte"] = _bound(dt, date_field, since)
        prev_filters[f"{date_field}__gte"] = _bound(dt, date_field, since - timedelta(days=days))
        prev_filters[f"{date_field}__lt"] = _bound(dt, date_field, since)

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
        # `filters` = exactly what the value was counted over, so the card can
        # drill down into the same rows of the list view.
        return {"value": val, "trend": trend, "filters": filters}
    except Exception:
        _log_widget_failed(doctype_name, widget.get("widget_type") or "metric")
        return {"value": 0, "trend": None}


async def _widget_chart(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """chart_area/chart_bar — a time series, optionally split into groups."""
    date_field = widget.get("date_field")
    if not date_field:
        return {"labels": [], "values": []}
    group_by = widget.get("group_by") or ""
    date_expr = f"date({date_field})"
    try:
        filters = {
            **base_filters,
            f"{date_field}__gte": _bound(dt, date_field, since),
            f"{date_field}__lte": _bound(dt, date_field, until, upper=True),
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
                (str(r.get(date_expr)), str(r.get(group_by))): int(r.get("cnt") or 0) for r in rows
            }
            groups = {gv: [lookup.get((lbl, gv), 0) for lbl in all_labels] for gv in group_values}
            return {"labels": all_labels, "groups": groups, "filters": filters}
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
                "filters": filters,
            }
    except Exception:
        _log_widget_failed(doctype_name, widget.get("widget_type") or "chart")
        return {"labels": [], "values": []}


async def _widget_donut(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """donut — top N groups by count."""
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
            # Raw group values (labels stringify NULL) + base filters, for drill-down.
            "keys": [r.get(group_by) for r in rows],
            "filters": base_filters,
        }
    except Exception:
        _log_widget_failed(doctype_name, "donut")
        return {"labels": [], "values": []}


async def _widget_list(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """list — most recently modified documents."""
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
        _log_widget_failed(doctype_name, "list")
        return {"items": [], "title_field": None}


async def _widget_shortcut(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """shortcut — a bare document count (always 1 for a singleton)."""
    try:
        if dt.is_singleton:
            return {"count": 1}
        return {"count": await grunt.count(doctype_name, filters=base_filters or None)}
    except Exception:
        _log_widget_failed(doctype_name, "shortcut")
        return None


async def _widget_calendar(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """calendar — document counts per calendar day, for the requested range."""
    date_field = widget.get("date_field")
    if not date_field:
        return {"days": {}}
    try:
        group_by_expr = f"date({date_field})"
        filters = {
            **base_filters,
            f"{date_field}__gte": _bound(dt, date_field, since),
            f"{date_field}__lte": _bound(dt, date_field, until, upper=True),
        }
        rows = await grunt.db.aggregate(
            doctype_name, filters=filters, group_by=group_by_expr, aggregations={"cnt": "count"}
        )
        return {"days": {str(r.get(group_by_expr)): r.get("cnt") for r in rows}}
    except Exception:
        _log_widget_failed(doctype_name, "calendar")
        return {"days": {}}


async def _widget_heatmap(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """heatmap — document counts per calendar day, since the range start (no upper bound)."""
    date_field = widget.get("date_field")
    if not date_field:
        return {"entries": []}
    try:
        group_by_expr = f"date({date_field})"
        filters = {**base_filters, f"{date_field}__gte": _bound(dt, date_field, since)}
        rows = await grunt.db.aggregate(
            doctype_name,
            filters=filters,
            group_by=group_by_expr,
            aggregations={"cnt": "count"},
            order_by=group_by_expr,
            order="asc",
        )
        return {
            "entries": [{"date": str(r.get(group_by_expr)), "count": r.get("cnt")} for r in rows],
            "filters": filters,
        }
    except Exception:
        _log_widget_failed(doctype_name, "heatmap")
        return {"entries": []}


async def _widget_funnel(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """funnel — group counts, ordered by a Select field's declared option order if available."""
    group_by = widget.get("group_by")
    if not group_by:
        return {"stages": []}
    try:
        from grunt.document.meta import Meta

        field_def = Meta(dt).get_field(group_by)
        ordered_options = []
        if field_def and field_def.options:
            ordered_options = [o for o in field_def.options.split("\n") if o.strip()]
        filters = dict(base_filters)
        date_field = widget.get("date_field")
        if date_field:
            filters[f"{date_field}__gte"] = _bound(dt, date_field, since)
        rows = await grunt.db.aggregate(
            doctype_name,
            filters=filters if filters else None,
            group_by=group_by,
            aggregations={"cnt": "count"},
        )
        counts = {r.get(group_by): r.get("cnt") for r in rows}
        if ordered_options:
            stages = [{"label": o, "key": o, "count": counts.get(o, 0)} for o in ordered_options]
        else:
            stages = [
                {"label": str(k), "key": k, "count": v}
                for k, v in sorted(counts.items(), key=lambda x: -(x[1] or 0))
            ]
        return {"stages": stages, "filters": filters}
    except Exception:
        _log_widget_failed(doctype_name, "funnel")
        return {"stages": []}


async def _widget_table(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """table — group aggregation rows (label + aggregated value), sorted descending."""
    group_by = widget.get("group_by")
    if not group_by:
        return {"rows": []}
    try:
        from grunt.document.meta import Meta

        agg = widget.get("aggregation") or "count"
        value_field = widget.get("field")
        agg_expr = f"{agg}({value_field})" if agg != "count" and value_field else "count"
        filters = dict(base_filters)
        date_field = widget.get("date_field")
        if date_field:
            filters[f"{date_field}__gte"] = _bound(dt, date_field, since)
            filters[f"{date_field}__lte"] = _bound(dt, date_field, until, upper=True)
        rows = await grunt.db.aggregate(
            doctype_name,
            filters=filters if filters else None,
            group_by=group_by,
            # _doc/_n let the widget open the document itself when rows are
            # grouped by the document's own title and the group is one row.
            aggregations={"value": agg_expr, "_doc": "min(name)", "_n": "count"},
            order_by="value",
            order="desc",
            limit=20,
        )
        group_field = Meta(dt).get_field(group_by)
        by_title = group_by in ("name", dt.title_field)
        return {
            "rows": [
                {
                    "label": str(r.get(group_by)) if r.get(group_by) is not None else "—",
                    "value": round(float(r.get("value") or 0), 2),
                    "key": r.get(group_by),
                    "doc": r.get("_doc") if by_title and r.get("_n") == 1 else None,
                }
                for r in rows
            ],
            "aggregation": agg,
            "field": value_field,
            "group_label": getattr(group_field, "label", None),
            "link_doctype": group_field.options
            if group_field and group_field.fieldtype == "Link"
            else None,
            "filters": filters,
        }
    except Exception:
        _log_widget_failed(doctype_name, "table")
        return {"rows": []}


async def _widget_activity(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """activity — recent ActivityLog entries, optionally scoped to one doctype."""
    from grunt.activity import feed_hidden_doctypes

    try:
        filters = dict(base_filters)
        if doctype_name:
            filters["doctype"] = doctype_name
        else:
            filters["doctype__nin"] = sorted(await feed_hidden_doctypes())
        items = await grunt.get_list(
            "ActivityLog", filters=filters, order_by="created_at", order="desc", limit=20
        )
        return {"items": items}
    except Exception:
        _log_widget_failed(doctype_name, "activity")
        return {"items": []}
