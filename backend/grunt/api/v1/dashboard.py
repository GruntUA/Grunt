"""Dashboard API — charts and number cards with aggregation queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

logger = structlog.get_logger()

router = APIRouter()

_TIMESPAN_DAYS = {
    "last_week": 7,
    "last_month": 30,
    "last_quarter": 90,
    "last_year": 365,
    "all_time": 0,
}

_AGGREGATION_FNS = {
    "count": func.count,
    "sum": func.sum,
    "avg": func.avg,
    "min": func.min,
    "max": func.max,
}


# ── Chart data ───────────────────────────────────────────────────────────


@router.get("/dashboard/charts")
async def list_charts(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all dashboard charts."""
    from grunt.core.db.system_tables import GruntDashboardChart  # noqa: PLC0415

    stmt = select(GruntDashboardChart).where(GruntDashboardChart.is_public.is_(True))
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return {
        "data": [
            {
                "id": r.id,
                "name": r.name,
                "chart_type": r.chart_type,
                "doctype": r.doctype,
                "value_field": r.value_field,
                "group_by": r.group_by,
                "timespan": r.timespan,
                "color": r.color,
            }
            for r in rows
        ]
    }


@router.get("/dashboard/chart/{chart_id}/data")
async def get_chart_data(
    chart_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Execute aggregation query for a dashboard chart."""
    from grunt.core.db.system_tables import GruntDashboardChart  # noqa: PLC0415

    stmt = select(GruntDashboardChart).where(GruntDashboardChart.id == chart_id)
    result = await session.execute(stmt)
    chart = result.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Графік не знайдено")

    dt = await doctype_registry.get(chart.doctype)
    table = compile_doctype_to_table(dt)

    value_col = table.c.get(chart.value_field)
    if value_col is None:
        raise HTTPException(status_code=400, detail=f"Поле '{chart.value_field}' не знайдено")

    # Build query
    if chart.group_by and chart.group_by in table.c:
        group_col = table.c[chart.group_by]
        query = select(group_col.label("label"), func.sum(value_col).label("value")).group_by(group_col)
    else:
        # Time-based grouping by created_at month
        if "created_at" in table.c:
            date_col = func.date_trunc("month", table.c.created_at).label("label")
            query = select(date_col, func.sum(value_col).label("value")).group_by(date_col).order_by(date_col)
        else:
            query = select(func.count().label("value"))

    # Timespan filter
    days = _TIMESPAN_DAYS.get(chart.timespan, 0)
    if days > 0 and "created_at" in table.c:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(table.c.created_at >= cutoff)

    # Extra filters
    if chart.filters:
        for field_name, field_value in chart.filters.items():
            if field_name in table.c:
                query = query.where(table.c[field_name] == field_value)

    result = await session.execute(query)
    rows = result.all()

    labels = []
    values = []
    for row in rows:
        mapping = row._mapping
        label = mapping.get("label", "Total")
        value = mapping.get("value", 0)
        if isinstance(label, datetime):
            label = label.strftime("%Y-%m")
        labels.append(str(label) if label else "—")
        values.append(float(value) if value else 0)

    return {
        "data": {
            "labels": labels,
            "values": values,
            "chart_type": chart.chart_type,
            "color": chart.color,
        }
    }


# ── Number cards ─────────────────────────────────────────────────────────


@router.get("/dashboard/cards")
async def list_number_cards(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all number cards."""
    from grunt.core.db.system_tables import GruntNumberCard  # noqa: PLC0415

    stmt = select(GruntNumberCard).where(GruntNumberCard.is_public.is_(True))
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return {
        "data": [
            {
                "id": r.id,
                "name": r.name,
                "label": r.label,
                "doctype": r.doctype,
                "aggregation": r.aggregation,
                "value_field": r.value_field,
                "color": r.color,
                "icon": r.icon,
            }
            for r in rows
        ]
    }


@router.get("/dashboard/card/{card_id}/data")
async def get_number_card_data(
    card_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Execute aggregation query for a number card."""
    from grunt.core.db.system_tables import GruntNumberCard  # noqa: PLC0415

    stmt = select(GruntNumberCard).where(GruntNumberCard.id == card_id)
    result = await session.execute(stmt)
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Картку не знайдено")

    dt = await doctype_registry.get(card.doctype)
    table = compile_doctype_to_table(dt)

    agg_fn = _AGGREGATION_FNS.get(card.aggregation, func.count)

    if card.aggregation == "count":
        query = select(agg_fn().label("value")).select_from(table)
    else:
        value_col = table.c.get(card.value_field)
        if value_col is None:
            raise HTTPException(status_code=400, detail=f"Поле '{card.value_field}' не знайдено")
        query = select(agg_fn(value_col).label("value")).select_from(table)

    # Extra filters
    if card.filters:
        for field_name, field_value in card.filters.items():
            if field_name in table.c:
                query = query.where(table.c[field_name] == field_value)

    result = await session.execute(query)
    row = result.one_or_none()
    value = float(row._mapping["value"]) if row and row._mapping["value"] else 0

    return {
        "data": {
            "value": value,
            "label": card.label,
            "color": card.color,
            "icon": card.icon,
        }
    }
