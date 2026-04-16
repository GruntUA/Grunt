"""Child table and MultiLink relationship management for Documents."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from grunt.core.document.validation import _coerce_value
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
from grunt.core.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.doctypes.user.user import User
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()


def _get_multi_link_fields(dt: DocType) -> list:
    """Return MultiLink fields from a DocType."""
    return [f for f in dt.fields if f.fieldtype == "MultiLink"]


async def _load_child_tables(session: AsyncSession, dt: DocType, doc: dict[str, Any]) -> None:
    """Attach child table rows to *doc* in-place for all TABLE fields."""
    for field in dt.fields:
        if field.fieldtype != "Table" or not field.options:
            continue
        try:
            child_dt = await doctype_registry.get(field.options)
            child_table = compile_doctype_to_table(child_dt)
            result = await session.execute(
                select(child_table)
                .where(child_table.c.parent_id == doc["id"])
                .order_by(child_table.c.idx)
            )
            rows = [dict(r._mapping) for r in result.all()]
            for row in rows:
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()
            doc[field.fieldname] = rows
        except Exception:
            logger.exception("child_table.load_error", doctype=dt.name, field=field.fieldname)
            doc[field.fieldname] = []


async def _save_child_tables(
    session: AsyncSession,
    dt: DocType,
    parent_id: str,
    data: dict[str, Any],
    user: User,
    now: datetime,
) -> None:
    """Replace child table rows for all TABLE fields present in *data*."""
    for field in dt.fields:
        if field.fieldtype != "Table" or not field.options:
            continue
        if field.fieldname not in data:
            continue
        child_rows = data[field.fieldname]
        if not isinstance(child_rows, list):
            child_rows = []
        try:
            child_dt = await doctype_registry.get(field.options)
            child_table = compile_doctype_to_table(child_dt)
            # Delete existing rows for this parent
            await session.execute(child_table.delete().where(child_table.c.parent_id == parent_id))
            # Build all rows then insert in one batch
            rows_to_insert: list[dict[str, Any]] = []
            for idx, child_data in enumerate(child_rows):
                if not isinstance(child_data, dict):
                    continue
                row: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    "name": str(uuid.uuid4())[:8],
                    "parent_id": parent_id,
                    "parent_doctype": dt.name,
                    "parent_field": field.fieldname,
                    "idx": child_data.get("idx", idx),
                    "owner": user.email,
                    "created_at": now,
                    "modified_at": now,
                    "modified_by": user.email,
                    "docstatus": 0,
                }
                for child_field in child_dt.fields:
                    if child_field.fieldtype in NON_PHYSICAL_FIELDS:
                        continue
                    if child_field.fieldname in child_data:
                        row[child_field.fieldname] = _coerce_value(
                            child_data[child_field.fieldname], child_field.fieldtype
                        )
                    elif child_field.default is not None:
                        row[child_field.fieldname] = _coerce_value(
                            child_field.default, child_field.fieldtype
                        )
                    else:
                        # Always include every column to avoid NOT NULL constraint
                        # errors. Use a type-appropriate empty value.
                        if child_field.fieldtype == "Check":
                            row[child_field.fieldname] = False
                        elif child_field.fieldtype in ("Int", "Float"):
                            row[child_field.fieldname] = 0
                        elif child_field.fieldtype in ("Date", "Datetime", "Time"):
                            row[child_field.fieldname] = None
                        else:
                            row[child_field.fieldname] = ""
                rows_to_insert.append(row)
            if rows_to_insert:
                await session.execute(child_table.insert(), rows_to_insert)
        except Exception:
            logger.exception(
                "child_table.save_error",
                doctype=dt.name,
                field=field.fieldname,
                parent_id=parent_id,
            )
