"""Dashboard API — widget data computation.

CRUD for Dashboard documents is handled by the standard /api/v1/docs/Dashboard/
endpoint.  This module provides only the data computation endpoint that runs
aggregation queries for each widget.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

router = APIRouter()

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}


# ── Widget data computation ────────────────────────────────────────────────


async def _compute_widget_data(widget: Any, session: AsyncSession) -> Any:
    """Compute data for a single widget row from the DocType table."""
    doctype_name: str = widget["doctype"] or ""
    if not doctype_name:
        return None

    try:
        dt = await doctype_registry.get(doctype_name)
    except Exception:
        logger.warning("dashboard.unknown_doctype", doctype=doctype_name)
        return None

    table = compile_doctype_to_table(dt)
    period_days = _PERIOD_DAYS.get(widget["period"] or "30d", 30)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=period_days)
    widget_type: str = widget["widget_type"] or "metric"

    if widget_type == "metric":
        agg = widget["aggregation"] or "count"
        field = widget["field"]
        if agg == "count":
            col = func.count()
        elif agg == "sum":
            col = func.sum(table.c[field]) if field and hasattr(table.c, field) else func.count()
        elif agg == "avg":
            col = func.avg(table.c[field]) if field and hasattr(table.c, field) else func.count()
        elif agg == "min":
            col = func.min(table.c[field]) if field and hasattr(table.c, field) else func.count()
        else:  # max
            col = func.max(table.c[field]) if field and hasattr(table.c, field) else func.count()

        date_field = widget["date_field"]
        if date_field and hasattr(table.c, date_field):
            stmt = select(col).where(table.c[date_field] >= since)
            prev_stmt = select(col).where(
                table.c[date_field] >= since - timedelta(days=period_days),
                table.c[date_field] < since,
            )
            r = await session.execute(stmt)
            r_prev = await session.execute(prev_stmt)
            val = r.scalar() or 0
            prev_val = r_prev.scalar() or 0
            trend = round((val - prev_val) / prev_val * 100, 1) if prev_val else None
        else:
            r = await session.execute(select(col))
            val = r.scalar() or 0
            trend = None

        return {"value": val, "trend": trend}

    if widget_type in ("chart_area", "chart_bar"):
        date_field = widget["date_field"]
        if not date_field or not hasattr(table.c, date_field):
            return {"labels": [], "values": []}

        try:
            day_expr = func.date(table.c[date_field])
            stmt = (
                select(day_expr.label("day"), func.count().label("cnt"))
                .where(table.c[date_field] >= since)
                .group_by(day_expr)
                .order_by(day_expr)
            )
            result = await session.execute(stmt)
            rows = result.all()
            return {"labels": [str(r.day) for r in rows], "values": [r.cnt for r in rows]}
        except Exception:
            logger.exception("dashboard.chart_error", widget_type=widget_type, doctype=doctype_name)
            return {"labels": [], "values": []}

    if widget_type == "donut":
        group_by = widget["group_by"]
        if not group_by or not hasattr(table.c, group_by):
            return {"labels": [], "values": []}
        try:
            stmt = (
                select(table.c[group_by].label("grp"), func.count().label("cnt"))
                .group_by(table.c[group_by])
                .order_by(text("cnt DESC"))
                .limit(8)
            )
            result = await session.execute(stmt)
            rows = result.all()
            return {"labels": [str(r.grp) for r in rows], "values": [r.cnt for r in rows]}
        except Exception:
            logger.exception("dashboard.donut_error", doctype=doctype_name)
            return {"labels": [], "values": []}

    if widget_type == "list":
        try:
            order_col = table.c["modified_at"] if hasattr(table.c, "modified_at") else table.c["created_at"]
            stmt = select(table).order_by(order_col.desc()).limit(8)
            result = await session.execute(stmt)
            items = [dict(r._mapping) for r in result.all()]
            for item in items:
                for k, v in item.items():
                    if isinstance(v, datetime):
                        item[k] = v.isoformat()
            return {"items": items, "title_field": dt.title_field}
        except Exception:
            logger.exception("dashboard.list_error", doctype=doctype_name)
            return {"items": [], "title_field": None}

    if widget_type == "shortcut":
        link_type = widget.get("link_type") or "DocType"
        if link_type != "DocType":
            return None
        target = doctype_name
        if not target:
            return None
        try:
            target_dt = await doctype_registry.get(target)
            target_table = compile_doctype_to_table(target_dt)
            r = await session.execute(select(func.count()).select_from(target_table))
            return {"count": r.scalar() or 0}
        except Exception:
            logger.warning("dashboard.shortcut_unknown_doctype", doctype=target)
            return None

    if widget_type == "shortcuts_grid":
        return None

    return None


@router.get("/dashboard-data/{name}")
async def get_dashboard_data(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return computed data for all widgets of a Dashboard document."""
    try:
        dashboard_dt = await doctype_registry.get("Dashboard")
        widget_dt = await doctype_registry.get("Dashboard Widget")
    except Exception:
        raise HTTPException(status_code=503, detail="Dashboard DocType не зареєстровано")

    dashboard_table = compile_doctype_to_table(dashboard_dt)
    widget_table = compile_doctype_to_table(widget_dt)

    result = await session.execute(
        select(dashboard_table).where(dashboard_table.c.name == name)
    )
    dashboard_row = result.first()
    if not dashboard_row:
        raise HTTPException(status_code=404, detail="Дашборд не знайдено")
    dashboard = dict(dashboard_row._mapping)

    if not user.is_superadmin and not dashboard["is_published"]:
        raise HTTPException(status_code=403, detail="Дашборд не опубліковано")

    widget_result = await session.execute(
        select(widget_table)
        .where(widget_table.c.parent_id == dashboard["id"])
        .order_by(widget_table.c.sequence)
    )
    widgets = widget_result.all()

    widget_data: dict[str, Any] = {}
    for w in widgets:
        w_dict = dict(w._mapping)
        try:
            widget_data[w_dict["id"]] = await _compute_widget_data(w_dict, session)
        except Exception as e:  # noqa: BLE001
            logger.warning("dashboard.widget_data_error", widget_id=w_dict.get("id"), error=str(e))
            widget_data[w_dict["id"]] = None

    return {"success": True, "data": widget_data}
