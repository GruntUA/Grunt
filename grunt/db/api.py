"""Grunt database API helpers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from sqlalchemy import CursorResult, func, or_, select, update

import grunt
from grunt import _
from grunt.db.buckets import DATE_BUCKETS, date_bucket
from grunt.db.filters import apply_filters, build_clauses
from grunt.errors import not_found
from grunt.local import _session_ctx
from grunt.utils.attr_dict import AttrDict

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy import Select, Table
    from sqlalchemy.ext.asyncio import AsyncSession

# "sum(amount)" / "count()" - see _parse_aggregation_expr.
_AGG_EXPR_RE = re.compile(r"^([a-z_]+)(?:\((.*)\))?$")
# "month(created_at)" / "date(due)" - see _build_group_by_column.
_GROUP_FN_RE = re.compile(rf"^(date|{'|'.join(DATE_BUCKETS)})\((.+)\)$", re.IGNORECASE)


def _parse_aggregation_expr(expr: str) -> tuple[str, str | None]:
    """Parse an ``aggregations`` DSL string into (function name, field name).

    ``field name`` is None for ``count()``/``count`` (no field required).
    Raises ValueError for anything that doesn't match ``fn(field)`` / ``fn``.
    """
    m = _AGG_EXPR_RE.match(expr.strip().lower())
    if not m:
        raise ValueError(f"Invalid aggregation expression: {expr}")
    fn_name, field = m.groups()
    return fn_name, (field.strip() if field else None)


def _build_aggregation_column(table: Any, fn_name: str, field_name: str | None) -> Any:
    """Build the SQLAlchemy aggregate-function column for a parsed DSL entry."""
    if fn_name == "count":
        return func.count()
    if not field_name or field_name == "*":
        raise ValueError(f"Function {fn_name} requires a field name.")
    if fn_name == "sum":
        return func.sum(table.c[field_name])
    if fn_name == "avg":
        return func.avg(table.c[field_name])
    if fn_name == "min":
        return func.min(table.c[field_name])
    if fn_name == "max":
        return func.max(table.c[field_name])
    raise ValueError(f"Unsupported aggregation function: {fn_name}")


def _build_group_by_column(table: Any, gb: str, dialect: str) -> tuple[Any, Any]:
    """Build (select_expr, group_by_expr) for one ``group_by`` entry.

    Supports a bare column name, ``date(field)`` (calendar day), or a period
    bucket ``day(field)`` / ``month(field)`` / ``quarter(field)`` /
    ``year(field)`` labelled ``2026-09-23`` / ``2026-09`` / ``2026-Q3`` / ``2026``.
    """
    gb = gb.strip()
    m = _GROUP_FN_RE.match(gb)
    if m:
        fn, field = m.group(1).lower(), m.group(2).strip()
        expr = (
            func.date(table.c[field]) if fn == "date" else date_bucket(table.c[field], fn, dialect)
        )
        return expr.label(gb), expr
    col = table.c[gb]
    return col.label(gb), col


class GruntDB:
    """Low-level database helpers - accessible as ``grunt.db``.

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

    @overload
    async def get_value(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldname: list[str],
        *,
        as_dict: Literal[False] = ...,
    ) -> list[Any] | None: ...

    @overload
    async def get_value(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldname: str | list[str],
        *,
        as_dict: Literal[True],
    ) -> AttrDict | None: ...

    @overload
    async def get_value(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldname: str = ...,
        *,
        as_dict: Literal[False] = ...,
    ) -> Any: ...

    async def get_value(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldname: str | list[str] = "name",
        *,
        as_dict: bool = False,
    ) -> Any:
        """Return field value(s) from the first document matching *filters*.

        *filters* may be a document name (``str``) or a filter dict::

            # single value
            subject = await grunt.db.get_value("Task", "TASK00002", "subject")

            # multiple values -> list (unpackable)
            subject, desc = await grunt.db.get_value(
                "Task", "TASK00002", ["subject", "description"]
            )

            # as attribute-dict
            task = await grunt.db.get_value(
                "Task", "TASK00002", ["subject", "description"], as_dict=True
            )
            task.subject

            # whole document
            task = await grunt.db.get_value("Task", "TASK00002", "*")

            # first record matching filters
            subject, desc = await grunt.db.get_value(
                "Task", {"status": "Open"}, ["subject", "description"]
            )

        Returns ``None`` when no document matches (or no requested field exists).
        """
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table

        async def _fetch_row(columns: list[Any]) -> Any:
            stmt = apply_filters(select(*columns), table, filters).limit(1)
            return (await self._session().execute(stmt)).first()

        # Whole-document fetch (``"*"``) - always returns an attribute-dict.
        if fieldname == "*":
            row = await _fetch_row([table])
            return AttrDict(row._mapping) if row is not None else None

        single = isinstance(fieldname, str)
        fields = [fieldname] if single else list(fieldname)
        present = [f for f in fields if f in table.c]
        if not present:
            return None

        row = await _fetch_row([table.c[f] for f in present])
        if row is None:
            return None
        values = dict(zip(present, row, strict=False))

        if as_dict:
            return AttrDict({f: values.get(f) for f in fields})
        if single:
            return values.get(fields[0])
        return [values.get(f) for f in fields]

    async def set_value(
        self,
        doctype: str,
        doc_id: str,
        fieldname: str | dict[str, Any],
        value: Any = None,
    ) -> None:
        """Update one or more fields on a document."""
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
        await self._session().execute(table.update().where(table.c.name == doc_id).values(values))
        await self._session().flush()

    async def exists(
        self,
        doctype: str,
        filters: str | dict[str, Any],
    ) -> str | None:
        """Return the document name if a match exists, else ``None``."""
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        stmt = select(table.c.name)
        stmt = apply_filters(stmt, table, filters)
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
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table

        select_fields = [pluck] if pluck else fields
        if select_fields:
            cols = [table.c[f] for f in select_fields if f in table.c]
            stmt = select(*cols) if cols else select(table)
        else:
            stmt = select(table)

        if filters:
            stmt = apply_filters(stmt, table, filters)

        if or_filters:
            or_clauses = build_clauses(table, or_filters)
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
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        cols = [table.c[f] for f in fieldnames if f in table.c]
        if not cols:
            return None

        stmt = select(*cols)
        stmt = apply_filters(stmt, table, filters)
        stmt = stmt.limit(1)
        result = await self._session().execute(stmt)
        row = result.first()
        if row is None:
            return None
        return dict(zip(fieldnames, row, strict=False))

    async def get_single_value(self, doctype: str, fieldname: str) -> Any:
        """Return a field value from a Singleton DocType (e.g. SystemSettings)."""
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        col = table.c.get(fieldname)
        if col is None:
            return None

        result = await self._session().execute(select(col).limit(1))
        row = result.first()
        return row[0] if row else None

    async def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        """Return a single document by name, or ``None`` if not found.

        Low-level - no permission guards. Use ``grunt.get_doc`` for
        authenticated reads with RBAC enforcement.
        """
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        stmt = select(table).where(table.c.name == name).limit(1)
        result = await self._session().execute(stmt)
        row = result.first()
        return dict(row._mapping) if row else None

    async def count(
        self,
        doctype: str,
        filters: dict[str, Any] | None = None,
        or_filters: dict[str, Any] | None = None,
    ) -> int:
        """Count documents matching optional filters (``or_filters`` - as in get_all)."""
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        stmt = select(func.count()).select_from(table)
        if filters:
            stmt = apply_filters(stmt, table, filters)
        if or_filters:
            or_clauses = build_clauses(table, or_filters)
            if or_clauses:
                stmt = stmt.where(or_(*or_clauses))
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

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table

        stmt = table.delete()
        stmt = apply_filters(stmt, table, filters)

        result = await self._session().execute(stmt)
        await self._session().flush()
        return cast("CursorResult", result).rowcount

    async def insert_one(self, doctype: str, values: dict[str, Any]) -> None:
        """Insert a single row into a DocType table and flush the session.

        This helper performs a direct table insert without lifecycle hooks.
        Caller is responsible for providing required standard fields
        (`name`, timestamps, owner, etc.) when needed.
        """
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        await self._session().execute(table.insert().values(**values))
        await self._session().flush()

    async def insert_many(self, doctype: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows into a DocType table and flush the session."""
        if not rows:
            return 0

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
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
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table

        update_values = {k: v for k, v in values.items() if k in table.c}
        if not update_values:
            return 0

        stmt = update(table).values(**update_values)
        stmt = apply_filters(stmt, table, filters)

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
        scope: Callable[[Select, Table], Awaitable[Select]] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch aggregated data (GROUP BY, SUM, COUNT, etc).

        No permission checks - ``grunt.aggregate`` is the permission-aware
        variant. ``scope`` lets it narrow the statement (row-level rules)
        before grouping.
        """
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table

        select_exprs: list[Any] = []
        group_by_exprs: list[Any] = []
        # label -> expression, so order_by can be resolved to a real construct
        # instead of being interpolated into raw SQL.
        labeled: dict[str, Any] = {}

        if isinstance(group_by, str):
            group_by = [group_by]

        dialect = self._session().bind.dialect.name
        for gb in group_by or []:
            select_expr, group_expr = _build_group_by_column(table, gb, dialect)
            select_exprs.append(select_expr)
            group_by_exprs.append(group_expr)
            labeled[gb.strip()] = select_expr

        for label, agg_expr in (aggregations or {}).items():
            fn_name, field_name = _parse_aggregation_expr(agg_expr)
            labeled_col = _build_aggregation_column(table, fn_name, field_name).label(label)
            select_exprs.append(labeled_col)
            labeled[label] = labeled_col

        if not select_exprs:
            select_exprs = [func.count().label("count")]

        # Explicit FROM: with no group_by/filter columns referenced, a bare
        # select(func.count()) has no FROM clause and returns a single row.
        stmt = select(*select_exprs).select_from(table)
        if filters:
            stmt = apply_filters(stmt, table, filters)
        if scope is not None:
            stmt = await scope(stmt, table)

        if group_by_exprs:
            stmt = stmt.group_by(*group_by_exprs)

        if order_by:
            # Resolve to a real construct (selected label or table column).
            # Never interpolate the caller's string into SQL: order_by reaches
            # here from app code and scripts, so a raw text() would be an
            # injection point.
            key = order_by.strip()
            expr = labeled.get(key)
            if expr is None:
                col = table.c.get(key)
                if col is None:
                    raise ValueError(f"Invalid order_by: {order_by!r}")
                expr = col
            stmt = stmt.order_by(expr.desc() if str(order).lower() == "desc" else expr.asc())

        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session().execute(stmt)
        return [dict(r._mapping) for r in result.all()]
