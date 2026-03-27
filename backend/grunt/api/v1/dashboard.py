"""Dashboard API — CRUD for dashboards + per-widget data computation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user, superadmin_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import compile_doctype_to_table, get_table_name
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

router = APIRouter()

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}


# ── Helpers ───────────────────────────────────────────────────────────────


def _widget_to_dict(w: Any) -> dict:
    return {
        "id": w.id,
        "dashboard_id": w.dashboard_id,
        "widget_type": w.widget_type,
        "title": w.title,
        "doctype": w.doctype,
        "field": w.field,
        "aggregation": w.aggregation,
        "group_by": w.group_by,
        "date_field": w.date_field,
        "period": w.period,
        "filters": w.filters or {},
        "cols": w.cols,
        "color": w.color,
        "icon": w.icon,
        "sequence": w.sequence,
    }


def _dashboard_to_dict(d: Any, *, with_widgets: bool = True) -> dict:
    result: dict = {
        "id": d.id,
        "name": d.name,
        "label": d.label,
        "description": d.description,
        "workspace": d.workspace,
        "roles": d.roles,
        "is_published": d.is_published,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "modified_at": d.modified_at.isoformat() if d.modified_at else None,
    }
    if with_widgets:
        result["widgets"] = [_widget_to_dict(w) for w in (d.widgets or [])]
    return result


async def _compute_widget_data(widget: Any, session: AsyncSession) -> dict:
    """Compute data for a single widget based on its type."""
    wtype = widget.widget_type

    try:
        dt = await doctype_registry.get(widget.doctype)
    except Exception:
        return {"error": f"DocType '{widget.doctype}' not found"}

    table = compile_doctype_to_table(dt)

    # Apply common filters
    def apply_filters(q: Any) -> Any:
        if widget.filters:
            for fname, fval in widget.filters.items():
                col = table.c.get(fname)
                if col is not None:
                    q = q.where(col == fval)
        return q

    # ── metric ────────────────────────────────────────────────────────
    if wtype == "metric":
        agg_map = {"count": func.count, "sum": func.sum, "avg": func.avg,
                   "min": func.min, "max": func.max}
        agg_fn = agg_map.get(widget.aggregation, func.count)

        if widget.aggregation == "count":
            q = select(agg_fn().label("v")).select_from(table)
        else:
            col = table.c.get(widget.field or "")
            if col is None:
                return {"error": f"Field '{widget.field}' not found"}
            q = select(agg_fn(col).label("v")).select_from(table)

        q = apply_filters(q)
        row = (await session.execute(q)).one_or_none()
        value = float(row._mapping["v"] or 0) if row else 0

        # Trend: compare current period vs previous period
        trend: float | None = None
        if widget.date_field:
            days = _PERIOD_DAYS.get(widget.period, 30)
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=days)
            prev_since = now - timedelta(days=days * 2)
            date_col = table.c.get(widget.date_field)
            if date_col is not None:
                if widget.aggregation == "count":
                    curr_q = select(func.count().label("v")).select_from(table).where(date_col >= since)
                    prev_q = select(func.count().label("v")).select_from(table).where(
                        date_col.between(prev_since, since)
                    )
                else:
                    col = table.c.get(widget.field or "")
                    if col is not None:
                        curr_q = select(agg_fn(col).label("v")).select_from(table).where(date_col >= since)
                        prev_q = select(agg_fn(col).label("v")).select_from(table).where(
                            date_col.between(prev_since, since)
                        )
                curr_val = (await session.execute(curr_q)).scalar() or 0
                prev_val = (await session.execute(prev_q)).scalar() or 0
                if prev_val:
                    trend = round((float(curr_val) - float(prev_val)) / float(prev_val) * 100, 1)

        return {"value": value, "trend": trend}

    # ── chart_area / chart_bar ────────────────────────────────────────
    if wtype in ("chart_area", "chart_bar"):
        days = _PERIOD_DAYS.get(widget.period, 30)
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)

        date_col = table.c.get(widget.date_field or "created_at")
        if date_col is None:
            date_col = table.c.get("created_at")
        if date_col is None:
            return {"labels": [], "values": []}

        # SQLite: strftime, PostgreSQL: to_char — use CAST to date
        q = (
            select(
                func.date(date_col).label("day"),
                func.count().label("cnt"),
            )
            .select_from(table)
            .where(date_col >= since)
            .group_by(func.date(date_col))
            .order_by(func.date(date_col))
        )
        q = apply_filters(q)
        rows = (await session.execute(q)).all()
        return {
            "labels": [str(r._mapping["day"]) for r in rows],
            "values": [int(r._mapping["cnt"]) for r in rows],
        }

    # ── donut ────────────────────────────────────────────────────────
    if wtype == "donut":
        group_col = table.c.get(widget.group_by or "")
        if group_col is None:
            return {"labels": [], "values": []}

        q = (
            select(group_col.label("grp"), func.count().label("cnt"))
            .select_from(table)
            .group_by(group_col)
            .order_by(func.count().desc())
            .limit(8)
        )
        q = apply_filters(q)
        rows = (await session.execute(q)).all()
        return {
            "labels": [str(r._mapping["grp"] or "—") for r in rows],
            "values": [int(r._mapping["cnt"]) for r in rows],
        }

    # ── list ──────────────────────────────────────────────────────────
    if wtype == "list":
        cols_to_select = [table.c["id"], table.c["name"]]
        if dt.title_field and dt.title_field in table.c:
            cols_to_select.append(table.c[dt.title_field])
        if "modified_at" in table.c:
            cols_to_select.append(table.c["modified_at"])

        q = (
            select(*cols_to_select)
            .select_from(table)
            .order_by(table.c.get("modified_at", table.c["name"]).desc())
            .limit(8)
        )
        q = apply_filters(q)
        rows = (await session.execute(q)).all()
        items = [dict(r._mapping) for r in rows]
        # Serialise datetimes
        for item in items:
            for k, v in item.items():
                if isinstance(v, datetime):
                    item[k] = v.isoformat()
        return {"items": items, "title_field": dt.title_field}

    return {}


# ── Dashboard CRUD ────────────────────────────────────────────────────────


@router.get("/dashboards/")
async def list_dashboards(
    workspace: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntDashboard  # noqa: PLC0415

    stmt = select(GruntDashboard)
    if workspace:
        stmt = stmt.where(GruntDashboard.workspace == workspace)
    if not user.is_superadmin:
        stmt = stmt.where(GruntDashboard.is_published.is_(True))

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return {"success": True, "data": [_dashboard_to_dict(r, with_widgets=False) for r in rows]}


@router.post("/dashboards/")
async def create_dashboard(
    body: dict,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntDashboard  # noqa: PLC0415

    name = body.get("name") or body.get("label", "").lower().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=422, detail="name є обов'язковим")

    existing = await session.execute(select(GruntDashboard).where(GruntDashboard.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Дашборд '{name}' вже існує")

    dashboard = GruntDashboard(
        id=str(uuid.uuid4()),
        name=name,
        label=body.get("label", name),
        description=body.get("description", ""),
        workspace=body.get("workspace"),
        roles=body.get("roles", ""),
        is_published=body.get("is_published", False),
    )
    session.add(dashboard)
    await session.flush()
    data = _dashboard_to_dict(dashboard, with_widgets=False)
    data["widgets"] = []
    return {"success": True, "data": data}


@router.get("/dashboards/{name}")
async def get_dashboard(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntDashboard  # noqa: PLC0415

    result = await session.execute(select(GruntDashboard).where(GruntDashboard.name == name))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Дашборд не знайдено")
    if not user.is_superadmin and not dashboard.is_published:
        raise HTTPException(status_code=403, detail="Дашборд не опубліковано")

    return {"success": True, "data": _dashboard_to_dict(dashboard)}


@router.put("/dashboards/{name}")
async def update_dashboard(
    name: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntDashboard, GruntDashboardWidget  # noqa: PLC0415
    from sqlalchemy import delete as sa_delete  # noqa: PLC0415

    result = await session.execute(select(GruntDashboard).where(GruntDashboard.name == name))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Дашборд не знайдено")

    dashboard.label = body.get("label", dashboard.label)
    dashboard.description = body.get("description", dashboard.description)
    dashboard.workspace = body.get("workspace", dashboard.workspace)
    dashboard.roles = body.get("roles", dashboard.roles)
    dashboard.is_published = body.get("is_published", dashboard.is_published)
    dashboard.modified_at = datetime.now(timezone.utc)

    # Replace widgets if provided
    if "widgets" in body:
        await session.execute(
            sa_delete(GruntDashboardWidget).where(GruntDashboardWidget.dashboard_id == dashboard.id)
        )
        await session.flush()
        for seq, w in enumerate(body["widgets"]):
            session.add(GruntDashboardWidget(
                id=w.get("id") or str(uuid.uuid4()),
                dashboard_id=dashboard.id,
                widget_type=w.get("widget_type", "metric"),
                title=w.get("title", ""),
                doctype=w.get("doctype", ""),
                field=w.get("field"),
                aggregation=w.get("aggregation", "count"),
                group_by=w.get("group_by"),
                date_field=w.get("date_field"),
                period=w.get("period", "30d"),
                filters=w.get("filters"),
                cols=w.get("cols", 1),
                color=w.get("color", "primary"),
                icon=w.get("icon"),
                sequence=w.get("sequence", seq),
            ))

    await session.flush()

    # Reload with widgets
    await session.refresh(dashboard)
    return {"success": True, "data": _dashboard_to_dict(dashboard)}


@router.delete("/dashboards/{name}")
async def delete_dashboard(
    name: str,
    session: AsyncSession = Depends(get_session),
    _: GruntUser = Depends(superadmin_user),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntDashboard  # noqa: PLC0415

    result = await session.execute(select(GruntDashboard).where(GruntDashboard.name == name))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Дашборд не знайдено")

    await session.delete(dashboard)
    await session.flush()
    return {"success": True}


@router.get("/dashboards/{name}/data")
async def get_dashboard_data(
    name: str,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict[str, Any]:
    """Return computed data for all widgets in a dashboard."""
    from grunt.core.db.system_tables import GruntDashboard  # noqa: PLC0415

    result = await session.execute(select(GruntDashboard).where(GruntDashboard.name == name))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Дашборд не знайдено")
    if not user.is_superadmin and not dashboard.is_published:
        raise HTTPException(status_code=403, detail="Дашборд не опубліковано")

    widget_data: dict[str, Any] = {}
    for widget in dashboard.widgets:
        try:
            widget_data[widget.id] = await _compute_widget_data(widget, session)
        except Exception as e:  # noqa: BLE001
            logger.warning("dashboard.widget_data_error", widget_id=widget.id, error=str(e))
            widget_data[widget.id] = {"error": str(e)}

    return {"success": True, "data": widget_data}


# ── Legacy endpoints (chart/card) kept for backwards compat ──────────────

@router.get("/dashboard/charts")
async def list_charts(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntDashboardChart  # noqa: PLC0415
    result = await session.execute(select(GruntDashboardChart))
    rows = result.scalars().all()
    return {"data": [{"id": r.id, "name": r.name, "chart_type": r.chart_type} for r in rows]}


@router.get("/dashboard/cards")
async def list_cards(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    from grunt.core.db.system_tables import GruntNumberCard  # noqa: PLC0415
    result = await session.execute(select(GruntNumberCard))
    rows = result.scalars().all()
    return {"data": [{"id": r.id, "name": r.name, "label": r.label} for r in rows]}
