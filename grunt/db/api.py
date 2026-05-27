"""Grunt database API helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, overload

from sqlalchemy import CursorResult, func, or_, select, update

from grunt.context import _session_ctx
from grunt.metadata.compiler import compile_doctype_to_table

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from grunt.metadata.registry import DocTypeRegistry


def _get_registry() -> "DocTypeRegistry":
    """Lazy import to avoid circular dependency grunt.db ↔ grunt.metadata.registry."""
    from grunt.metadata.registry import doctype_registry  # noqa: PLC0415
    return doctype_registry


class GruntDB:
    """Low-level database helpers — accessible as ``grunt.db``.

    All methods are async and operate on the current request session.

    Example::

        name = await grunt.db.get_value("Customer", {"tax_id": "123"}, "full_name")
        await grunt.db.set_value("Customer", customer_id, "status", "Active")
        exists = await grunt.db.exists("Customer", {"email": "a@b.com"})
        rows = await grunt.db.get_all("Customer", filters={"status": "Active"}, limit=10)
    """

    def _session(self) -> AsyncSession:
        s = _session_ctx.get()
        if s is None:
            raise RuntimeError("grunt.db: no active session — are you inside a request or hook?")
        return s

    async def get_value(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldname: str,
    ) -> Any:
        """Return a single field value from the first matching document."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        col = table.c.get(fieldname)
        if col is None:
            return None

        stmt = select(col)
        stmt = _apply_filters(stmt, table, filters)
        stmt = stmt.limit(1)
        result = await self._session().execute(stmt)
        row = result.first()
        return row[0] if row else None

    async def set_value(
        self,
        doctype: str,
        doc_id: str,
        fieldname: str | dict[str, Any],
        value: Any = None,
    ) -> None:
        """Update one or more fields on a document."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
        await self._session().execute(table.update().where(table.c.name == doc_id).values(values))
        await self._session().flush()

    async def exists(
        self,
        doctype: str,
        filters: str | dict[str, Any],
    ) -> str | None:
        """Return the document name if a match exists, else ``None``."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        stmt = select(table.c.name)
        stmt = _apply_filters(stmt, table, filters)
        stmt = stmt.limit(1)
        result = await self._session().execute(stmt)
        row = result.first()
        return row[0] if row else None

    @overload
    async def get_all(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = ...,
        or_filters: dict[str, Any] | None = ...,
        fields: list[str] | None = ...,
        pluck: str,
        limit: int | None = ...,
        offset: int = ...,
        order_by: str | None = ...,
        order: str = ...,
    ) -> list[Any]: ...

    @overload
    async def get_all(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = ...,
        or_filters: dict[str, Any] | None = ...,
        fields: list[str] | None = ...,
        pluck: None = ...,
        limit: int | None = ...,
        offset: int = ...,
        order_by: str | None = ...,
        order: str = ...,
    ) -> list[dict[str, Any]]: ...

    async def get_all(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        or_filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        pluck: str | None = None,
        limit: int | None = 20,
        offset: int = 0,
        order_by: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, Any]] | list[Any]:
        """Fetch a list of documents as plain dicts."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)

        select_fields = [pluck] if pluck else fields
        if select_fields:
            cols = [table.c[f] for f in select_fields if f in table.c]
            stmt = select(*cols) if cols else select(table)
        else:
            stmt = select(table)

        if filters:
            stmt = _apply_db_filters(stmt, table, filters)

        if or_filters:
            or_clauses = _build_clauses(table, or_filters)
            if or_clauses:
                stmt = stmt.where(or_(*or_clauses))

        sort_col = table.c.get(order_by or "modified_at")
        if sort_col is None:
            sort_col = table.c.get("created_at")
        if sort_col is not None:
            stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())

        if limit is not None:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        result = await self._session().execute(stmt)
        rows = result.fetchall()

        if pluck:
            return [row[0] for row in rows]
        return [dict(row._mapping) for row in rows]

    async def get_values(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldnames: list[str],
    ) -> dict[str, Any] | None:
        """Return multiple field values from the first matching document."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        cols = [table.c[f] for f in fieldnames if f in table.c]
        if not cols:
            return None

        stmt = select(*cols)
        stmt = _apply_filters(stmt, table, filters)
        stmt = stmt.limit(1)
        result = await self._session().execute(stmt)
        row = result.first()
        if row is None:
            return None
        return dict(zip(fieldnames, row, strict=False))

    async def get_single_value(self, doctype: str, fieldname: str) -> Any:
        """Return a field value from a Singleton DocType (e.g. SystemSettings)."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        col = table.c.get(fieldname)
        if col is None:
            return None

        result = await self._session().execute(select(col).limit(1))
        row = result.first()
        return row[0] if row else None

    async def count(
        self,
        doctype: str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Count documents matching optional filters."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        stmt = select(func.count()).select_from(table)
        if filters:
            stmt = _apply_db_filters(stmt, table, filters)
        result = await self._session().execute(stmt)
        return result.scalar() or 0

    async def delete(
        self,
        doctype: str,
        filters: dict[str, Any],
    ) -> int:
        """Bulk-delete documents matching filters without running lifecycle hooks."""
        if not filters:
            raise ValueError("grunt.db.delete requires at least one filter.")

        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)

        stmt = table.delete()
        stmt = _apply_db_filters(stmt, table, filters)

        result = await self._session().execute(stmt)
        await self._session().flush()
        return cast("CursorResult", result).rowcount

    async def insert_one(self, doctype: str, values: dict[str, Any]) -> None:
        """Insert a single row into a DocType table and flush the session.

        This helper performs a direct table insert without lifecycle hooks.
        Caller is responsible for providing required standard fields
        (`name`, timestamps, owner, etc.) when needed.
        """
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        await self._session().execute(table.insert().values(**values))
        await self._session().flush()

    async def insert_many(self, doctype: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows into a DocType table and flush the session."""
        if not rows:
            return 0

        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)
        result = await self._session().execute(table.insert(), rows)
        await self._session().flush()
        return cast("CursorResult", result).rowcount or len(rows)

    async def bulk_update(
        self,
        doctype: str,
        filters: dict[str, Any],
        values: dict[str, Any],
    ) -> int:
        """Update multiple rows matching exact-match filters and flush session."""
        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)

        update_values = {k: v for k, v in values.items() if k in table.c}
        if not update_values:
            return 0

        stmt = update(table).values(**update_values)
        stmt = _apply_db_filters(stmt, table, filters)

        result = await self._session().execute(stmt)
        await self._session().flush()
        return cast("CursorResult", result).rowcount or 0

    async def aggregate(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | list[str] | None = None,
        aggregations: dict[str, str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Fetch aggregated data (GROUP BY, SUM, COUNT, etc)."""
        import re

        from sqlalchemy import text

        dt = await _get_registry().get(doctype)
        table = compile_doctype_to_table(dt)

        select_exprs: list[Any] = []
        group_by_exprs: list[Any] = []

        if isinstance(group_by, str):
            group_by = [group_by]

        if group_by:
            for gb in group_by:
                gb = gb.strip()
                if gb.startswith("date(") and gb.endswith(")"):
                    field = gb[5:-1].strip()
                    expr = func.date(table.c[field]).label(gb)
                    select_exprs.append(expr)
                    group_by_exprs.append(func.date(table.c[field]))
                else:
                    expr = table.c[gb].label(gb)
                    select_exprs.append(expr)
                    group_by_exprs.append(table.c[gb])

        if aggregations:
            for label, agg_expr in aggregations.items():
                agg_expr = agg_expr.strip().lower()
                m = re.match(r"^([a-z_]+)(?:\((.*)\))?$", agg_expr)
                if not m:
                    raise ValueError(f"Invalid aggregation expression: {agg_expr}")
                fn_name, field = m.groups()
                field_name: str | None = field.strip() if field else None

                col: Any
                if fn_name == "count":
                    col = func.count()
                else:
                    if not field_name or field_name == "*":
                        raise ValueError(f"Function {fn_name} requires a field name.")
                    if fn_name == "sum":
                        col = func.sum(table.c[field_name])
                    elif fn_name == "avg":
                        col = func.avg(table.c[field_name])
                    elif fn_name == "min":
                        col = func.min(table.c[field_name])
                    elif fn_name == "max":
                        col = func.max(table.c[field_name])
                    else:
                        raise ValueError(f"Unsupported aggregation function: {fn_name}")

                select_exprs.append(col.label(label))

        if not select_exprs:
            select_exprs = [func.count().label("count")]

        stmt = select(*select_exprs)
        if filters:
            stmt = _apply_db_filters(stmt, table, filters)

        if group_by_exprs:
            stmt = stmt.group_by(*group_by_exprs)

        if order_by:
            stmt = stmt.order_by(text(f"{order_by} {order.upper()}"))

        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session().execute(stmt)
        return [dict(r._mapping) for r in result.all()]


# ── Internal helpers ─────────────────────────────────────────────────────────


def _apply_filters(stmt: Any, table: Any, filters: str | dict[str, Any]) -> Any:
    """Apply name (str) or operator-aware dict filters to a statement."""
    if isinstance(filters, str):
        stmt = stmt.where(table.c.name == filters)
    elif isinstance(filters, dict):
        stmt = _apply_db_filters(stmt, table, filters)
    return stmt


_FILTER_OPS = ("__gte", "__lte", "__gt", "__lt", "__like", "__in", "__nin", "__ne", "__isnull")


def _build_clauses(table: Any, filters: dict[str, Any]) -> list[Any]:
    """Build SQLAlchemy WHERE clauses from a filter dict."""
    clauses: list[Any] = []
    for key, value in filters.items():
        op = "eq"
        fieldname = key
        for suffix in _FILTER_OPS:
            if key.endswith(suffix):
                fieldname = key[: -len(suffix)]
                op = suffix[2:]
                break
        col = table.c.get(fieldname)
        if col is None:
            continue
        if op == "eq":
            clauses.append(col == value)
        elif op == "gte":
            clauses.append(col >= value)
        elif op == "lte":
            clauses.append(col <= value)
        elif op == "gt":
            clauses.append(col > value)
        elif op == "lt":
            clauses.append(col < value)
        elif op == "like":
            clauses.append(col.like(f"%{value}%"))
        elif op == "in":
            clauses.append(col.in_(value))
        elif op == "nin":
            clauses.append(col.not_in(value))
        elif op == "ne":
            clauses.append(col != value)
        elif op == "isnull":
            if value:
                clauses.append(col.is_(None))
            else:
                clauses.append(col.isnot(None))
    return clauses


def _apply_db_filters(stmt: Any, table: Any, filters: dict[str, Any]) -> Any:
    """Apply AND-filters with operator suffixes to a statement."""
    for clause in _build_clauses(table, filters):
        stmt = stmt.where(clause)
    return stmt


# Backward-compatible module proxy:
# Some code paths use `import grunt` and call `grunt.db.get_all(...)`.
# In that case, `grunt.db` may resolve to this module object instead of the
# API singleton from `grunt.api`. Forward unknown attributes to a shared
# GruntDB instance so both styles remain valid.
_db_proxy = GruntDB()


def __getattr__(name: str):
    if hasattr(_db_proxy, name):
        return getattr(_db_proxy, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
