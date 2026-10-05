"""Aggregation field computation for parent documents.

Aggregate fields pull a summary value (sum/count/avg/min/max) from a child
TABLE field into a scalar column on the parent row.  They are recomputed
every time child table rows are saved.

Example field definition (in the parent DocType JSON):
    {
        "fieldname": "total_amount",
        "fieldtype": "Float",
        "label": "Total Amount",
        "aggregate_function": "sum",
        "aggregate_table": "items",       # fieldname of the TABLE field
        "aggregate_field": "amount"       # fieldname in the child DocType
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from grunt import log
from grunt.document.meta import Meta

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.metadata.doctype import DocType


async def compute_aggregations(
    session: AsyncSession,
    dt: DocType,
    parent_id: str,
) -> dict[str, Any]:
    """Compute all aggregate fields for *parent_id* and return a mapping
    of ``{fieldname: value}`` for each field that has an aggregate_function.

    Returns an empty dict if no aggregate fields are defined.
    """
    import grunt

    meta = Meta(dt)
    agg_fields = meta.get_aggregate_fields()
    if not agg_fields:
        return {}

    results: dict[str, Any] = {}

    # Group by (aggregate_table, aggregate_function) to batch DB queries
    # where possible, but simplest is one query per aggregate field.
    for field in agg_fields:
        func_name = (field.aggregate_function or "").lower()
        table_fieldname = field.aggregate_table
        child_col = field.aggregate_field

        if not table_fieldname:
            log.warning(
                "aggregate.missing_table",
                doctype=dt.name,
                fieldname=field.fieldname,
            )
            continue

        # Find the TABLE field in the parent DocType to get child doctype name
        table_field = meta.get_field(table_fieldname)
        if table_field is None or table_field.fieldtype != "Table" or not table_field.options:
            log.warning(
                "aggregate.table_field_not_found",
                doctype=dt.name,
                aggregate_table=table_fieldname,
            )
            continue

        child_dt = await grunt.get_meta(table_field.options)
        if child_dt is None:
            log.warning(
                "aggregate.child_doctype_not_found",
                doctype=dt.name,
                child_doctype=table_field.options,
            )
            continue

        child_table = child_dt.table

        # "count" does not need a child column
        if func_name == "count":
            stmt = (
                select(func.count())
                .select_from(child_table)
                .where(child_table.c.parent_name == parent_id)
            )
        else:
            if not child_col or child_col not in child_table.c:
                log.warning(
                    "aggregate.child_column_not_found",
                    doctype=dt.name,
                    child_doctype=table_field.options,
                    aggregate_field=child_col,
                )
                continue

            col = child_table.c[child_col]
            agg_func = {
                "sum": func.sum,
                "avg": func.avg,
                "min": func.min,
                "max": func.max,
            }.get(func_name)

            if agg_func is None:
                log.warning(
                    "aggregate.unknown_function",
                    function=func_name,
                    fieldname=field.fieldname,
                )
                continue

            stmt = select(agg_func(col)).where(child_table.c.parent_name == parent_id)

        try:
            row = (await session.execute(stmt)).one()
            value = row[0]
        except Exception:
            log.exception(
                "aggregate.query_error",
                doctype=dt.name,
                fieldname=field.fieldname,
            )
            continue

        # Coerce None -> 0 for numeric functions (sum/avg/count/min/max)
        if value is None:
            value = 0

        results[field.fieldname] = value

    return results
