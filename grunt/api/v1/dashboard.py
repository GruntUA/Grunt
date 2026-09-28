"""Dashboard whitelisted methods for widget computation."""

from __future__ import annotations

import contextlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import grunt
from grunt.i18n import _
from grunt.log import log
from grunt.metadata.widget import get_widget_type_class
from grunt.reports.widget_compute import _widget_report_series

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


async def _compute_widget_data(
    widget: Any,
    global_since: datetime | None = None,
    global_until: datetime | None = None,
) -> Any:
    """Compute data for a single widget row — dispatches via the WidgetType registry."""
    from grunt.app import grunt as grunt_app

    doctype_name: str = widget.get("doctype") or ""
    widget_type: str = widget.get("widget_type") or "metric"

    cls = get_widget_type_class(widget_type)
    if cls is None or not cls.requires_backend_compute:
        return None

    # A chart/donut widget may draw its data from a saved Report rather than a
    # doctype aggregate — that path needs no doctype/date_field/group_by.
    if widget.get("report") and widget_type in ("chart_bar", "chart_area", "donut"):
        return await _widget_report_series(widget)

    if not doctype_name and cls.requires_doctype:
        return None

    dt = None
    if doctype_name:
        dt = await grunt_app.get_meta(doctype_name)
        if dt is None:
            log.warning("dashboard.unknown_doctype", doctype=doctype_name)
            return None

    period_key = widget.get("period") or "last_month"
    days = _TIMESPAN_DAYS.get(period_key, 30)
    now = datetime.now(UTC)
    since = global_since if global_since is not None else now - timedelta(days=days)
    until = global_until if global_until is not None else now
    base_filters = _widget_filters(widget)
    tree_filters = {k: v for k, v in base_filters.items() if k.endswith("__child_of")}
    if not tree_filters or dt is None:
        return await cls.compute(widget, dt, doctype_name, since, until, days, base_filters)

    # `field__child_of` is expanded to the subtree (`field__in=…`) only by list
    # queries; grunt.db.aggregate would silently drop it, so expand it here.
    from grunt.document.query import _expand_child_of_filters

    session = grunt_app._require_session()
    expanded = await _expand_child_of_filters(session, dt.doc, base_filters)
    data = await cls.compute(widget, dt, doctype_name, since, until, days, expanded)
    # The list URL can't carry `__in`, so drill-down gets the original child_of back.
    if isinstance(data, dict) and isinstance(data.get("filters"), dict):
        for key, value in tree_filters.items():
            field = key.removesuffix("__child_of")
            data["filters"].pop(f"{field}__in", None)
            data["filters"].pop(f"{field}__eq", None)
            data["filters"][key] = value
    return data


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
    if "System Manager" not in (user.roles or []) and not dashboard.get("is_published"):
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

    # Sequential, not asyncio.gather: all widgets share the request-scoped
    # AsyncSession, which SQLAlchemy does not allow to be driven from
    # concurrent coroutines — gathering here races queries onto the same
    # session and raises IllegalStateChangeError under load.
    pairs = [await _safe_compute(w) for w in widgets]
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
        not_found_msg=_("Page not found"),
        unpublished_msg=_("The page is not published"),
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
        not_found_msg=_("Dashboard not found"),
        unpublished_msg=_("The dashboard is not published"),
    )
