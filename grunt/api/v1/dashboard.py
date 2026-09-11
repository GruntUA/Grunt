"""Dashboard whitelisted methods for widget computation."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import grunt
from grunt.log import log

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


_RELATIVE_DATE_RE = re.compile(r"^@(today|now)(?:\s*([+-])\s*(\d+)([dwmy]))?$", re.IGNORECASE)

_RELATIVE_UNIT_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}


def _resolve_relative_date(value: Any) -> Any:
    """Resolve ``@today`` / ``@now`` tokens into concrete ISO date strings.

    Dashboard filters live in static fixtures, so they cannot hardcode a date
    without silently rotting. Tokens are resolved at query time instead:

        "@today"        -> 2026-07-22
        "@today-7d"     -> 2026-07-15
        "@today+30d"    -> 2026-08-21   (d=days, w=weeks, m=30d, y=365d)
        "@now"          -> full ISO timestamp

    Non-matching values are returned untouched, so plain dates still work.
    """
    if not isinstance(value, str):
        return value
    match = _RELATIVE_DATE_RE.match(value.strip())
    if match is None:
        return value

    base_token, sign, amount, unit = match.groups()
    now = datetime.now(UTC)
    if sign and amount and unit:
        delta = timedelta(days=int(amount) * _RELATIVE_UNIT_DAYS[unit.lower()])
        now = now - delta if sign == "-" else now + delta

    return now.isoformat() if base_token.lower() == "now" else now.date().isoformat()


def _widget_filters(widget: Any) -> dict[str, Any]:
    """Return the widget's filters as a dict, with relative dates resolved.

    The ``filters`` field is declared as JSON, so it may arrive either already
    decoded (dict) or as a raw JSON string depending on the storage backend.
    Anything unparseable is treated as "no filters" rather than failing the
    whole widget.
    """
    raw = widget.get("filters")
    if not raw:
        return {}

    if isinstance(raw, dict):
        parsed: Any = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except TypeError, ValueError:
            log.warning("dashboard.bad_filters", filters=raw)
            return {}
    else:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return {key: _resolve_relative_date(value) for key, value in parsed.items()}


def _log_widget_failed(doctype_name: str, widget_type: str) -> None:
    log.warning(
        "dashboard.widget_failed",
        doctype=doctype_name,
        widget_type=widget_type,
        exc_info=True,
    )


def _as_number(value: Any) -> float:
    """Best-effort numeric coercion for report cell values."""
    if isinstance(value, (int, float)):
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
    from grunt.app import grunt as grunt_app
    from grunt.reports.engine import report_engine

    report_name = widget.get("report") or ""
    try:
        user = grunt_app._require_user()
        session = grunt_app._require_session()

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
                (str(r.get(date_expr)), str(r.get(group_by))): int(r.get("cnt") or 0) for r in rows
            }
            groups = {gv: [lookup.get((lbl, gv), 0) for lbl in all_labels] for gv in group_values}
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
            f"{date_field}__gte": since.isoformat(),
            f"{date_field}__lte": until.isoformat(),
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
            "entries": [{"date": str(r.get(group_by_expr)), "count": r.get("cnt")} for r in rows]
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
        _log_widget_failed(doctype_name, "funnel")
        return {"stages": []}


async def _widget_table(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """table — group aggregation rows (label + aggregated value), sorted descending."""
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
        _log_widget_failed(doctype_name, "table")
        return {"rows": []}


async def _widget_activity(widget, dt, doctype_name, since, until, days, base_filters) -> Any:
    """activity — recent ActivityLog entries, optionally scoped to one doctype."""
    from grunt.activity import FEED_HIDDEN_DOCTYPES

    try:
        filters = dict(base_filters)
        if doctype_name:
            filters["doctype"] = doctype_name
        else:
            filters["doctype__nin"] = sorted(FEED_HIDDEN_DOCTYPES)
        items = await grunt.get_list(
            "ActivityLog", filters=filters, order_by="created_at", order="desc", limit=20
        )
        return {"items": items}
    except Exception:
        _log_widget_failed(doctype_name, "activity")
        return {"items": []}


# widget_type -> handler. Multiple types can share a handler (metric/gauge,
# chart_area/chart_bar) when they compute data identically.
_WIDGET_HANDLERS = {
    "metric": _widget_metric,
    "gauge": _widget_metric,
    "chart_area": _widget_chart,
    "chart_bar": _widget_chart,
    "donut": _widget_donut,
    "list": _widget_list,
    "shortcut": _widget_shortcut,
    "calendar": _widget_calendar,
    "heatmap": _widget_heatmap,
    "funnel": _widget_funnel,
    "table": _widget_table,
    "activity": _widget_activity,
}


async def _compute_widget_data(
    widget: Any,
    global_since: datetime | None = None,
    global_until: datetime | None = None,
) -> Any:
    """Compute data for a single widget row — dispatches on widget_type."""
    from grunt.metadata.registry import doctype_registry

    doctype_name: str = widget.get("doctype") or ""
    widget_type: str = widget.get("widget_type") or "metric"

    # A chart/donut widget may draw its data from a saved Report rather than a
    # doctype aggregate — that path needs no doctype/date_field/group_by.
    if widget.get("report") and widget_type in ("chart_bar", "chart_area", "donut"):
        return await _widget_report_series(widget)

    if not doctype_name and widget_type != "activity":
        return None

    dt = None
    if doctype_name:
        try:
            dt = await doctype_registry.get(doctype_name)
        except Exception:
            log.warning("dashboard.unknown_doctype", doctype=doctype_name, exc_info=True)
            return None

    period_key = widget.get("period") or "last_month"
    days = _TIMESPAN_DAYS.get(period_key, 30)
    now = datetime.now(UTC)
    since = global_since if global_since is not None else now - timedelta(days=days)
    until = global_until if global_until is not None else now
    base_filters = _widget_filters(widget)

    handler = _WIDGET_HANDLERS.get(widget_type)
    if handler is None:
        return None
    return await handler(widget, dt, doctype_name, since, until, days, base_filters)


async def _get_widget_data(
    entity_doctype: str,
    name: str,
    date_from: str | None,
    date_to: str | None,
    *,
    not_found_msg: str,
    unpublished_msg: str,
) -> dict[str, Any]:
    """Compute all widget values for a Page/Dashboard document.

    Shared by get_page_data/get_dashboard_data — identical widget-computation
    pipeline for both entity types, differing only in which doctype to load
    and the (localized) error messages.
    """
    from grunt.app import grunt as grunt_app

    doc = await grunt.find_doc(entity_doctype, name)
    if doc is None:
        grunt.throw(not_found_msg, "NOT_FOUND")
    dashboard = dict(doc)

    user = grunt_app._require_user()
    if not user.is_superadmin and not dashboard.get("is_published"):
        grunt.throw(unpublished_msg, "PERMISSION_DENIED")

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
            log.warning(
                "dashboard.widget_compute_failed",
                widget=w_dict.get("name"),
                exc_info=True,
            )
            result = None
        return w_dict["name"], result

    pairs = await asyncio.gather(*(_safe_compute(w) for w in widgets))
    return dict(pairs)


@grunt.whitelist()
async def get_page_data(
    name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Return computed data for all widgets of a Page document."""
    return await _get_widget_data(
        "Page",
        name,
        date_from,
        date_to,
        not_found_msg="Сторінку не знайдено",
        unpublished_msg="Сторінку не опубліковано",
    )


@grunt.whitelist()
async def get_dashboard_data(
    name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Return computed data for all widgets of a Dashboard document."""
    return await _get_widget_data(
        "Dashboard",
        name,
        date_from,
        date_to,
        not_found_msg="Дашборд не знайдено",
        unpublished_msg="Дашборд не опубліковано",
    )
