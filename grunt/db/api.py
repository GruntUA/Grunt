"""Grunt database API helpers."""

from typing import Any, Literal, cast, overload

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import _
from grunt.errors import not_found
from grunt.local import _session_ctx
from grunt.query import run
from grunt.query.nodes import TRUE, Expr, and_, conjuncts, or_
from grunt.query.query import Query, Sort
from grunt.query.sql import filter_expr, where
from grunt.utils.attr_dict import AttrDict
lazy from grunt.document.multi_link import MultiLinkService


def list_query(
    dt: Any,
    *,
    filters: str | dict[str, Any] | None = None,
    or_filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    order_by: str | None = None,
    order: str = "desc",
) -> Query:
    """A :class:`Query` from ``grunt.db``-style arguments: *filters* ANDed,
    *or_filters* ORed (unknown columns skipped in both), sorted by *order_by*
    (``modified_at`` by default)."""
    any_of = conjuncts(filter_expr(or_filters, dt.columns, dt)) if or_filters else ()
    return Query(
        dt.name,
        where=and_(filter_expr(filters, dt.columns, dt), or_(*any_of) if any_of else TRUE),
        fields=tuple(fields) if fields else None,
        sort=Sort(order_by or "modified_at", descending=order != "asc"),
        limit=limit,
        offset=offset,
    )


def aggregate_query(
    dt: Any,
    *,
    filters: dict[str, Any] | None = None,
    group_by: str | list[str] | None = None,
    aggregations: dict[str, str] | None = None,
    limit: int | None = None,
    order_by: str | None = None,
    order: str = "desc",
) -> Query:
    """A :class:`Query` for :meth:`Store.aggregate` from ``grunt.db.aggregate`` arguments."""
    groups = [group_by] if isinstance(group_by, str) else list(group_by or [])
    return Query(
        dt.name,
        where=filter_expr(filters, dt.columns, dt),
        group_by=tuple(groups),
        aggregates=tuple((aggregations or {}).items()),
        sort=Sort(order_by, descending=str(order).lower() == "desc") if order_by else None,
        limit=limit,
    )


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

    @staticmethod
    async def _meta(doctype: str) -> Any:
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        return dt

    @staticmethod
    def _require_filter(expr: Expr, doctype: str, action: str) -> None:
        """A bulk write whose filters all name unknown columns would hit every row."""
        if expr == TRUE:
            raise ValueError(
                f"grunt.db.{action}({doctype!r}): no filter names a column - refusing to "
                "touch every row"
            )

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
        dt = await self._meta(doctype)

        async def first(fields: list[str] | None) -> dict[str, Any] | None:
            query = Query(
                doctype,
                where=filter_expr(filters, dt.columns, dt),
                fields=tuple(fields) if fields else None,
                limit=1,
            )
            rows = await run.fetch(query, ignore_permissions=True, session=self._session())
            return rows[0] if rows else None

        # Whole-document fetch (``"*"``) - always returns an attribute-dict.
        if fieldname == "*":
            row = await first(None)
            return AttrDict(row) if row is not None else None

        single = isinstance(fieldname, str)
        fields = [fieldname] if single else list(fieldname)
        present = [f for f in fields if f in dt.table.c]
        if not present:
            return None

        values = await first(present)
        if values is None:
            return None
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
        """Update one or more fields on a document.

        A MultiLink field takes a list of linked names and replaces its junction rows.
        """
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
        multilinks = {f.fieldname: f for f in dt.get_multilink_fields() if f.fieldname in values}
        if multilinks:
            service = MultiLinkService(self._session())
            for key, field in multilinks.items():
                await service.set_values(
                    dt.name, doc_id, key, field.options or "", list(values[key] or [])
                )
            values = {k: v for k, v in values.items() if k not in multilinks}
        # A raw write skips coerce (NULLs stay NULL), but markup is still sanitized.
        values = {
            key: field.coerce(val)
            if (field := dt.get_field(key)) and field.has_trait("html")
            else val
            for key, val in values.items()
        }
        if values:
            await self._session().execute(
                table.update().where(table.c.name == doc_id).values(values)
            )
        await self._session().flush()

    async def exists(
        self,
        doctype: str,
        filters: str | dict[str, Any],
    ) -> str | None:
        """Return the document name if a match exists, else ``None``."""
        dt = await self._meta(doctype)
        query = Query(
            doctype, where=filter_expr(filters, dt.columns, dt), fields=("name",), limit=1
        )
        rows = await run.fetch(query, ignore_permissions=True, session=self._session())
        return rows[0]["name"] if rows else None

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
        """Fetch a list of documents as plain dicts.

        No permission checks - ``grunt.get_all`` is the permission-aware
        variant (both are :func:`grunt.query.run.fetch`). A MultiLink
        field in ``fields`` comes back as a list of linked names (one extra
        query for the whole page).
        """
        dt = await self._meta(doctype)
        query = list_query(
            dt,
            filters=filters,
            or_filters=or_filters,
            fields=[pluck] if pluck else fields,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order=order,
        )
        rows = await run.fetch(query, ignore_permissions=True, session=self._session())
        if pluck:
            return [row.get(pluck) for row in rows]
        return rows

    async def get_values(
        self,
        doctype: str,
        filters: str | dict[str, Any],
        fieldnames: list[str],
    ) -> dict[str, Any] | None:
        """Return multiple field values from the first matching document."""
        dt = await self._meta(doctype)
        present = [f for f in fieldnames if f in dt.table.c]
        if not present:
            return None
        query = Query(
            doctype, where=filter_expr(filters, dt.columns, dt), fields=tuple(present), limit=1
        )
        rows = await run.fetch(query, ignore_permissions=True, session=self._session())
        return {f: rows[0].get(f) for f in present} if rows else None

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
        dt = await self._meta(doctype)
        query = list_query(dt, filters=filters, or_filters=or_filters)
        return await run.count(query, ignore_permissions=True, session=self._session())

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

        expr = filter_expr(filters, dt.columns, dt)
        self._require_filter(expr, doctype, "delete")
        stmt = await where(table.delete(), expr, table, dt.name)

        result = await self._session().execute(stmt)
        await self._session().flush()
        return cast(CursorResult, result).rowcount

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
        return cast(CursorResult, result).rowcount or len(rows)

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

        expr = filter_expr(filters, dt.columns, dt)
        self._require_filter(expr, doctype, "bulk_update")
        stmt = await where(update(table).values(**update_values), expr, table, dt.name)

        result = await self._session().execute(stmt)
        await self._session().flush()
        return cast(CursorResult, result).rowcount or 0

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
        """Fetch aggregated data (GROUP BY, SUM, COUNT, etc).

        No permission checks - ``grunt.aggregate`` is the permission-aware
        variant. ``group_by`` entries may bucket a date: ``date(field)``,
        ``day/month/quarter/year(field)``. ``order_by`` - a group or an
        aggregation label, or a column.
        """
        dt = await self._meta(doctype)
        query = aggregate_query(
            dt,
            filters=filters,
            group_by=group_by,
            aggregations=aggregations,
            limit=limit,
            order_by=order_by,
            order=order,
        )
        return await run.aggregate(query, ignore_permissions=True, session=self._session())
