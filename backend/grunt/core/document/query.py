"""Query and filter building for DocumentService."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import or_

if TYPE_CHECKING:
    from grunt.core.metadata.doctype import DocType


def _apply_filters(query: Any, table: Any, filters: dict[str, str]) -> Any:
    """Apply operator-aware dictionary filters to a statement."""
    for key, value in filters.items():
        if "__" in key:
            fieldname, op = key.rsplit("__", 1)
        else:
            fieldname, op = key, "eq"

        col = table.c.get(fieldname)
        if col is None:
            continue

        if op == "eq":
            query = query.where(col == value)
        elif op == "gte":
            query = query.where(col >= value)
        elif op == "lte":
            query = query.where(col <= value)
        elif op == "gt":
            query = query.where(col > value)
        elif op == "lt":
            query = query.where(col < value)
        elif op == "like":
            query = query.where(col.like(f"%{value}%"))
        elif op == "ilike":
            query = query.where(col.ilike(f"%{value}%"))
        elif op == "in":
            query = query.where(col.in_(value.split(",")))
        elif op in ("ne", "neq"):
            query = query.where(col != value)
        elif op == "isnull":
            if value.lower() in ("true", "1"):
                query = query.where(col.is_(None))
            else:
                query = query.where(col.isnot(None))

    return query


def _apply_search(query: Any, table: Any, dt: DocType, search: str) -> Any:
    """Apply full-text search conditions to a statement."""
    search_cols = []
    if dt.search_fields:
        for fname in dt.search_fields:
            col = table.c.get(fname)
            if col is not None:
                search_cols.append(col)
    if not search_cols:
        search_cols = [table.c.name]

    conditions = [col.ilike(f"%{search}%") for col in search_cols]
    return query.where(or_(*conditions))
