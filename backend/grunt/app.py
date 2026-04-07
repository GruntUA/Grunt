"""Grunt developer API — the primary interface for building apps on the Grunt framework.

This module provides a high-level, async-first API for app developers, similar to
how `frappe` works in the Frappe framework. It is context-aware: the current
database session, engine, and user are automatically injected via ContextVars that
are set by the framework at the start of each request / lifecycle hook call.

Typical usage in a DocType controller::

    from grunt.app import grunt

    class Invoice(Document):
        number: str
        amount: float
        status: str

        async def validate(self) -> None:
            if self.amount <= 0:
                grunt.throw("Сума повинна бути більше нуля")

        async def after_insert(self) -> None:
            await grunt.notify(
                users=[self.owner],
                subject=f"Рахунок {self.number} створено",
                message=f"Новий рахунок на суму {self.amount} грн.",
                doctype=self.doctype,
                doc_id=self.id,
            )

Typical usage in a server script (already available as ``grunt``)::

    doc = grunt.get_doc("Invoice", params.get("id"))
    grunt.db.set_value("Invoice", doc["id"], "status", "Paid")

Typical usage in a hook function::

    from grunt.app import grunt

    async def on_invoice_save(doc, user, **kwargs):
        if doc["status"] == "Paid":
            await grunt.publish(user=doc["owner"], event="msgprint",
                                message="Оплату підтверджено", type="success")
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, or_, select

from grunt.core.context import _engine_ctx, _session_ctx, _user_ctx
from grunt.core.db.profiler import profile
from grunt.core.metadata.compiler import compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()


# ── GruntError ────────────────────────────────────────────────────────────────


class GruntError(Exception):
    """User-facing error raised via ``grunt.throw()``.

    Caught by DocumentService and returned as an HTTP 422 response.
    """

    def __init__(self, message: str, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


# ── DB helpers ────────────────────────────────────────────────────────────────


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
        """Return a single field value from the first matching document.

        Args:
            doctype: DocType name.
            filters: Document id/name (str) or filter dict, e.g. ``{"email": "a@b.com"}``.
            fieldname: Field to return.

        Returns:
            Field value, or ``None`` if no document matches.
        """
        dt = await doctype_registry.get(doctype)
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
        """Update one or more fields on a document.

        Args:
            doctype: DocType name.
            doc_id: Document id or name.
            fieldname: Field name (str) or a dict of {field: value} pairs.
            value: New value (ignored when fieldname is a dict).
        """
        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
        await self._session().execute(
            table.update()
            .where((table.c.id == doc_id) | (table.c.name == doc_id))
            .values(values)
        )
        await self._session().flush()

    async def exists(
        self,
        doctype: str,
        filters: str | dict[str, Any],
    ) -> str | None:
        """Return the document name if a match exists, else ``None``.

        Args:
            doctype: DocType name.
            filters: Document id/name (str) or filter dict.

        Returns:
            Document ``name`` value, or ``None``.
        """
        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        stmt = select(table.c.name)
        stmt = _apply_filters(stmt, table, filters)
        stmt = stmt.limit(1)
        result = await self._session().execute(stmt)
        row = result.first()
        return row[0] if row else None

    async def get_all(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        or_filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        pluck: str | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, Any]] | list[Any]:
        """Fetch a list of documents as plain dicts.

        Args:
            doctype: DocType name.
            filters: AND-conditions. Supports operator suffixes:
                ``{"status": "Active"}``              → ``status = 'Active'``
                ``{"amount__gte": 1000}``             → ``amount >= 1000``
                ``{"amount__lte": 5000}``             → ``amount <= 5000``
                ``{"amount__gt": 0}``                 → ``amount > 0``
                ``{"amount__lt": 9999}``              → ``amount < 9999``
                ``{"name__like": "%Іван%"}``          → ``name LIKE '%Іван%'``
                ``{"status__in": ["Draft", "Open"]}`` → ``status IN (...)``
            or_filters: OR-conditions (same operator syntax as ``filters``).
                Combined with ``filters`` as: ``filters AND (or_filter1 OR or_filter2 ...)``.
            fields: Field names to return. Defaults to all fields.
            pluck: If set, return a flat list of values for this single field
                instead of a list of dicts, e.g. ``pluck="email"`` →
                ``["a@b.com", "c@d.com"]``.
            limit: Maximum number of rows (default 20).
            order_by: Field name to sort by (default: ``modified_at``).
            order: Sort direction — ``"asc"`` or ``"desc"`` (default: ``"desc"``).

        Returns:
            List of dicts, or a flat list of values when ``pluck`` is set.
        """
        dt = await doctype_registry.get(doctype)
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

        stmt = stmt.limit(limit)
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
        """Return multiple field values from the first matching document.

        Args:
            doctype: DocType name.
            filters: Document id/name (str) or filter dict.
            fieldnames: List of fields to return.

        Returns:
            Dict ``{fieldname: value}`` or ``None`` if no document matches.

        Example::

            data = await grunt.db.get_values("User", "admin@grunt.local", ["full_name", "email"])
            # {"full_name": "Admin", "email": "admin@grunt.local"}
        """
        dt = await doctype_registry.get(doctype)
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
        return dict(zip(fieldnames, row))

    async def get_single_value(self, doctype: str, fieldname: str) -> Any:
        """Return a field value from a Singleton DocType (e.g. SystemSettings).

        Args:
            doctype: Singleton DocType name.
            fieldname: Field to return.

        Returns:
            Field value, or ``None`` if the singleton has no record yet.

        Example::

            lang = await grunt.db.get_single_value("SystemSettings", "language")
        """
        dt = await doctype_registry.get(doctype)
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
        """Count documents matching optional filters.

        Convenience alias — identical to ``grunt.count(doctype, filters=...)``.

        Example::

            total = await grunt.db.count("Order", {"status": "Open"})
        """
        dt = await doctype_registry.get(doctype)
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
        """Bulk-delete documents matching filters **without** running lifecycle hooks.

        Use :meth:`~grunt.app.GruntApp.delete_doc` when hooks must run.

        Args:
            doctype: DocType name.
            filters: Conditions selecting documents to delete (same operator
                syntax as :meth:`get_all`). At least one filter is required to
                prevent accidental full-table deletion.

        Returns:
            Number of deleted rows.

        Example::

            deleted = await grunt.db.delete("TempLog", {"created_at__lt": cutoff})
        """
        if not filters:
            raise ValueError("grunt.db.delete requires at least one filter to prevent accidental full-table deletion.")

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)

        stmt = table.delete()
        stmt = _apply_db_filters(stmt, table, filters)

        result = await self._session().execute(stmt)
        await self._session().flush()
        return result.rowcount  # type: ignore[return-value]

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

        Args:
            doctype: DocType name.
            filters: Filter matching documents.
            group_by: Column name(s) or functions like `date(created_at)`.
            aggregations: Dict mapping output column name to agg function
                e.g. ``{"cnt": "count", "total": "sum(amount)"}``.
            limit: Maximum number of rows.
            order_by: Fallback order_by column or alias.
            order: "asc" or "desc".

        Returns:
            List of dicts with aggregated data.
        """
        import re  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)

        select_exprs = []
        group_by_exprs = []

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
                m = re.match(r'^([a-z_]+)(?:\((.*)\))?$', agg_expr)
                if not m:
                    raise ValueError(f"Invalid aggregation expression: {agg_expr}")
                fn_name, field = m.groups()
                field = field.strip() if field else None
                
                if fn_name == "count":
                    col = func.count()
                else:
                    if not field or field == "*":
                        raise ValueError(f"Function {fn_name} requires a field name.")
                    if fn_name == "sum":
                        col = func.sum(table.c[field])
                    elif fn_name == "avg":
                        col = func.avg(table.c[field])
                    elif fn_name == "min":
                        col = func.min(table.c[field])
                    elif fn_name == "max":
                        col = func.max(table.c[field])
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


# ── Session info ──────────────────────────────────────────────────────────────


class GruntSession:
    """Current request session information — accessible as ``grunt.session``.

    Example::

        if grunt.session.is_superadmin:
            ...
        current_user = grunt.session.user
    """

    @property
    def user(self) -> str:
        """Email of the current user, or ``"guest@grunt.local"`` for unauthenticated requests."""
        u = _user_ctx.get()
        return u.email if u else "guest@grunt.local"

    @property
    def full_name(self) -> str:
        """Full name of the current user."""
        u = _user_ctx.get()
        return u.full_name if u else "Guest"

    @property
    def roles(self) -> list[str]:
        """List of role names assigned to the current user."""
        u = _user_ctx.get()
        return u.roles if u else []

    @property
    def is_superadmin(self) -> bool:
        """Whether the current user is a superadmin."""
        u = _user_ctx.get()
        return u.is_superadmin if u else False

    def has_role(self, *roles: str) -> bool:
        """Return True if the current user has any of the given roles."""
        user_roles = set(self.roles)
        return bool(user_roles.intersection(roles))


# ── Main API ──────────────────────────────────────────────────────────────────


class GruntApp:
    """Primary developer API for building Grunt apps.

    Accessed via the module-level singleton ``grunt``:

    .. code-block:: python

        from grunt.app import grunt

        # CRUD
        doc = await grunt.get_doc("Invoice", invoice_id)
        new_invoice = await grunt.new_doc("Invoice", {"number": "INV-001", "amount": 1500.0})
        updated = await grunt.save_doc("Invoice", invoice_id, {"status": "Paid"})
        await grunt.delete_doc("Invoice", invoice_id)

        # List / count
        items = await grunt.get_list("Product", filters={"active": True}, limit=50)
        total = await grunt.count("Product", filters={"active": True})

        # DB shortcuts
        name = await grunt.db.get_value("Customer", customer_id, "full_name")
        await grunt.db.set_value("Invoice", invoice_id, "status", "Paid")

        # Meta
        meta = await grunt.get_meta("Invoice")

        # Notifications
        await grunt.notify(users=["user@example.com"], subject="Paid", message="...")
        await grunt.publish(user="user@example.com", event="msgprint", message="Done")

        # Error handling
        grunt.throw("Validation failed")

        # Current user
        print(grunt.session.user)
    """

    def __init__(self) -> None:
        self.db = GruntDB()
        self.session = GruntSession()

    # ── Context management ────────────────────────────────────────────────

    def set_context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
        user: GruntUser | None = None,
    ) -> tuple:
        """Set the request context (session / engine / user).

        Called automatically by :class:`~grunt.core.document.service.DocumentService`
        before invoking lifecycle hooks. Returns a tuple of ContextVar tokens that
        can be passed to :meth:`reset_context` to restore the previous state.

        App developers generally do NOT need to call this directly.
        """
        return (
            _session_ctx.set(session),
            _engine_ctx.set(engine),
            _user_ctx.set(user),
        )

    def reset_context(self, tokens: tuple) -> None:
        """Restore the context to its previous state using tokens from :meth:`set_context`."""
        _session_ctx.reset(tokens[0])
        _engine_ctx.reset(tokens[1])
        _user_ctx.reset(tokens[2])

    def _require_session(self) -> AsyncSession:
        s = _session_ctx.get()
        if s is None:
            raise RuntimeError("grunt: no active session — are you inside a request context or lifecycle hook?")
        return s

    def _require_engine(self) -> AsyncEngine:
        e = _engine_ctx.get()
        if e is None:
            raise RuntimeError("grunt: no active engine.")
        return e

    def _require_user(self) -> GruntUser:
        u = _user_ctx.get()
        if u is None:
            raise RuntimeError("grunt: no active user.")
        return u

    # ── Document CRUD ─────────────────────────────────────────────────────

    def _svc(self):
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        return DocumentService(self._require_session(), self._require_engine())

    @profile("grunt.get_doc")
    async def get_doc(self, doctype: str, id_or_name: str) -> dict[str, Any]:
        """Fetch a single document by id or name.

        Args:
            doctype: DocType name, e.g. ``"Invoice"``.
            id_or_name: Document id (UUID) or name (human-readable identifier).

        Returns:
            Document as a plain dict.

        Raises:
            :class:`~fastapi.HTTPException` (404) if not found.
        """
        return await self._svc().get_document(doctype, id_or_name, self._require_user())

    async def new_doc(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new document and return it.

        Runs all lifecycle hooks (``validate``, ``before_insert``, ``after_insert``,
        ``before_save``, ``after_save``).

        Args:
            doctype: DocType name.
            data: Field values for the new document.

        Returns:
            The created document as a plain dict (includes generated ``id`` and ``name``).
        """
        return await self._svc().create_document(doctype, data, self._require_user())

    async def save_doc(
        self,
        doctype: str,
        id_or_name: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing document and return the updated version.

        Runs ``validate``, ``before_save``, ``after_save`` hooks.

        Args:
            doctype: DocType name.
            id_or_name: Document id or name.
            data: Fields to update (partial update — omitted fields are unchanged).

        Returns:
            The updated document as a plain dict.
        """
        return await self._svc().update_document(doctype, id_or_name, data, self._require_user())

    async def delete_doc(self, doctype: str, id_or_name: str) -> None:
        """Delete a document.

        Runs ``before_delete`` and ``after_delete`` hooks.

        Args:
            doctype: DocType name.
            id_or_name: Document id or name.
        """
        await self._svc().delete_document(doctype, id_or_name, self._require_user())

    @profile("grunt.get_list")
    async def get_list(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        page: int = 1,
        order_by: str = "modified_at",
        order: str = "desc",
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a list of documents.

        Args:
            doctype: DocType name.
            filters: Filter dict, e.g. ``{"status": "Active", "amount__gte": "1000"}``.
            fields: Field names to return. Defaults to all fields.
            limit: Max documents per page (default 20).
            page: Page number (default 1).
            order_by: Sort field (default ``"modified_at"``).
            order: Sort direction — ``"asc"`` or ``"desc"`` (default ``"desc"``).
            search: Full-text search string.

        Returns:
            List of document dicts.
        """
        result = await self._svc().list_documents(
            doctype,
            self._require_user(),
            page=page,
            per_page=limit,
            sort_by=order_by,
            sort_order=order,
            filters=filters,
            search=search,
            fields=fields,
        )
        return result["data"]

    async def bulk_insert(
        self,
        doctype: str,
        records: list[dict[str, Any]],
    ) -> list[str]:
        """Create multiple documents in a single database round-trip.

        Each record is validated and enriched with system fields (id, name,
        owner, created_at, modified_at, docstatus) before bulk insert.
        Lifecycle hooks (validate / before_insert / after_insert) are NOT
        called — use :meth:`new_doc` in a loop for hook support.

        Args:
            doctype: DocType name.
            records: List of field-value dicts.

        Returns:
            List of generated document ids (in the same order as ``records``).
        """
        import uuid  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415
        from sqlalchemy import insert  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        user = self._require_user()
        session = self._require_session()

        now = datetime.now(timezone.utc).isoformat()
        rows: list[dict[str, Any]] = []
        ids: list[str] = []

        for rec in records:
            doc_id = str(uuid.uuid4())
            ids.append(doc_id)
            row = {
                "id": doc_id,
                "name": rec.get("name") or doc_id,
                "owner": user.email,
                "created_at": now,
                "modified_at": now,
                "modified_by": user.email,
                "docstatus": 0,
                **{k: v for k, v in rec.items() if k in table.c},
            }
            rows.append(row)

        await session.execute(insert(table).values(rows))
        await session.flush()
        logger.info("grunt.bulk_insert", doctype=doctype, count=len(rows))
        return ids

    async def bulk_update(
        self,
        doctype: str,
        filters: dict[str, Any],
        values: dict[str, Any],
    ) -> int:
        """Update multiple documents matching ``filters`` in a single query.

        Lifecycle hooks are NOT called — use :meth:`save_doc` in a loop when
        hooks are required.

        Args:
            doctype: DocType name.
            filters: Filter dict matching documents to update, e.g.
                ``{"status": "Pending"}``.
            values: Fields to set, e.g. ``{"status": "Archived"}``.

        Returns:
            Number of rows updated.
        """
        from datetime import datetime, timezone  # noqa: PLC0415
        from sqlalchemy import update  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        session = self._require_session()
        user = self._require_user()

        stmt = update(table).values(
            **{k: v for k, v in values.items() if k in table.c},
            modified_at=datetime.now(timezone.utc).isoformat(),
            modified_by=user.email,
        )
        for key, val in filters.items():
            col = table.c.get(key)
            if col is not None:
                stmt = stmt.where(col == val)

        result = await session.execute(stmt)
        await session.flush()
        row_count: int = result.rowcount  # type: ignore[assignment]
        logger.info("grunt.bulk_update", doctype=doctype, rows=row_count)
        return row_count

    @profile("grunt.count")
    async def count(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Count documents matching optional filters.

        Args:
            doctype: DocType name.
            filters: Filter dict.

        Returns:
            Number of matching documents.
        """
        return await self.db.count(doctype, filters=filters)

    # ── Meta ──────────────────────────────────────────────────────────────

    async def get_meta(self, doctype: str) -> DocType:
        """Return the :class:`~grunt.core.metadata.doctype.DocType` definition.

        Args:
            doctype: DocType name.

        Returns:
            DocType pydantic model instance.
        """
        return await doctype_registry.get(doctype)

    # ── Notifications / realtime ──────────────────────────────────────────

    async def notify(
        self,
        *,
        users: list[str],
        subject: str,
        message: str,
        doctype: str | None = None,
        doc_id: str | None = None,
        push: bool = True,
    ) -> list[str]:
        """Create persistent bell notifications for one or more users.

        Args:
            users: List of user emails to notify.
            subject: Notification title.
            message: Notification body.
            doctype: Related DocType (optional).
            doc_id: Related document id (optional).
            push: Whether to also push via WebSocket (default ``True``).

        Returns:
            List of created notification ids.
        """
        from grunt.publish import notify as _notify  # noqa: PLC0415

        return await _notify(
            users=users,
            subject=subject,
            message=message,
            session=self._require_session(),
            doctype=doctype,
            doc_id=doc_id,
            push=push,
        )

    async def publish(
        self,
        user: str,
        event: str,
        data: dict[str, Any] | None = None,
        *,
        message: str | None = None,
        type: str = "info",
    ) -> None:
        """Send a transient WebSocket message to a specific user (not persisted).

        Common events: ``"msgprint"``, ``"alert"``, ``"progress"``, ``"notification"``.

        Args:
            user: Recipient email.
            event: Event name.
            data: Arbitrary payload dict.
            message: Convenience shorthand — adds ``data["message"]``.
            type: Message type for UI styling: ``"success"``, ``"error"``, ``"info"``, ``"warning"``.
        """
        from grunt.publish import publish as _publish  # noqa: PLC0415

        await _publish(user=user, event=event, data=data, message=message, type=type)  # type: ignore[arg-type]

    async def broadcast(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        *,
        message: str | None = None,
        type: str = "info",
    ) -> None:
        """Broadcast a transient WebSocket message to ALL connected users.

        Args:
            event: Event name.
            data: Arbitrary payload dict.
            message: Convenience shorthand.
            type: Message type for UI styling.
        """
        from grunt.publish import broadcast as _broadcast  # noqa: PLC0415

        await _broadcast(event=event, data=data, message=message, type=type)  # type: ignore[arg-type]

    # ── Error handling ────────────────────────────────────────────────────

    def throw(self, message: str, title: str | None = None) -> None:
        """Raise a user-facing :class:`GruntError`.

        The error is caught by :class:`~grunt.core.document.service.DocumentService`
        and returned to the client as an HTTP 422 response.

        Args:
            message: Error message shown to the user.
            title: Optional dialog title.

        Raises:
            :class:`GruntError`: always.
        """
        raise GruntError(message, title=title)

    async def msgprint(
        self,
        msg: str | list,
        title: str | None = None,
        *,
        indicator: str = "blue",
        as_list: bool = False,
        as_table: bool = False,
        raise_exception: type[BaseException] | None = None,
    ) -> None:
        """Show a message dialog to the current user via WebSocket.

        Unlike :meth:`throw`, this method does **not** abort the request —
        the message is displayed as a non-blocking dialog/toast in the UI.

        Args:
            msg: Message string, or a list of strings (``as_list=True``),
                or a list of row-lists (``as_table=True``).
            title: Dialog heading.
            indicator: Colour indicator — ``"blue"`` (default), ``"green"``,
                ``"red"``, ``"orange"``, ``"yellow"``.
            as_list: Render ``msg`` (a ``list[str]``) as an HTML ``<ul>``.
            as_table: Render ``msg`` (a ``list[list]``) as an HTML ``<table>``.
            raise_exception: If provided, raise this exception type after
                sending the message (mirrors ``frappe.msgprint``'s behaviour).

        Raises:
            The type passed to ``raise_exception``, if given.

        Example — simple toast::

            await grunt.msgprint("Документ успішно збережено", indicator="green")

        Example — list of items::

            await grunt.msgprint(
                ["Поле A порожнє", "Поле B невірне"],
                title="Попередження",
                indicator="orange",
                as_list=True,
            )

        Example — table::

            await grunt.msgprint(
                [["Назва", "Сума"], ["Рахунок-1", "1 200"], ["Рахунок-2", "800"]],
                title="Деталі",
                as_table=True,
            )

        Example — message + raise::

            await grunt.msgprint(
                "Файл не знайдено",
                indicator="red",
                raise_exception=FileNotFoundError,
            )
        """
        formatted = _format_msgprint(msg, as_list=as_list, as_table=as_table)

        _INDICATOR_TO_TYPE = {
            "blue": "info",
            "green": "success",
            "red": "error",
            "orange": "warning",
            "yellow": "warning",
        }
        msg_type = _INDICATOR_TO_TYPE.get(indicator, "info")

        await self.publish(
            user=self.session.user,
            event="msgprint",
            data={"title": title, "indicator": indicator},
            message=formatted,
            type=msg_type,
        )

        if raise_exception is not None:
            raise raise_exception(formatted)

    def log(self, *args: Any) -> None:
        """Log a message via structlog (also captured in server script output)."""
        logger.info("grunt.log", message=" ".join(str(a) for a in args))

    # ── i18n shorthand ────────────────────────────────────────────────────

    def _(self, source: str) -> str:
        """Translate a string using the current request language."""
        from grunt.core.i18n import _ as _translate  # noqa: PLC0415

        return _translate(source)

    # ── Templates ─────────────────────────────────────────────────────────

    async def render_template(
        self,
        template: str,
        context: dict[str, Any] | None = None,
        *,
        autoescape: bool = True,
    ) -> str:
        """Render a Jinja2 template and return the result as a string.

        The following globals are automatically available in every template:

        * ``grunt`` — the :class:`GruntApp` singleton (all SDK methods usable
          via ``await``, e.g. ``{% set doc = await grunt.get_doc(...) %}``).
        * ``session`` — shorthand for ``grunt.session``.
        * ``_`` — shorthand for ``grunt._()`` (translation).
        * ``now`` — current UTC datetime.

        Args:
            template: Template **file name** (e.g. ``"notification_digest.html"``)
                or an **inline template string** (e.g. ``"Hello {{ name }}!"``).
                Treated as a file name when it ends with a known extension
                (``.html``, ``.txt``, ``.md``, ``.xml``, ``.jinja``, ``.j2``).
            context: Extra variables passed to the template.
            autoescape: HTML auto-escaping (default ``True``).
                Pass ``False`` for plain-text / Markdown templates.

        Returns:
            Rendered string.

        Example — file template::

            html = await grunt.render_template(
                "notification_digest.html",
                {"groups": groups, "total": 42},
            )

        Example — inline string::

            text = await grunt.render_template(
                "Привіт, {{ name }}! У вас {{ count }} повідомлень.",
                {"name": "Іван", "count": 3},
                autoescape=False,
            )

        Example — using grunt globals inside a template::

            {# templates/invoice_email.html #}
            {% set invoice = await grunt.get_doc("Invoice", invoice_id) %}
            <p>Рахунок № {{ invoice.name }} на суму {{ invoice.amount }} грн.</p>
            <p>{{ _("Дякуємо за співпрацю!") }}</p>
            <p>{{ session.full_name }}</p>
        """
        from datetime import datetime, timezone  # noqa: PLC0415
        from jinja2 import Environment, FileSystemLoader, DictLoader, select_autoescape  # noqa: PLC0415

        ctx = context or {}
        _FILE_EXTENSIONS = (".html", ".txt", ".md", ".xml", ".jinja", ".j2")
        is_file = any(template.endswith(ext) for ext in _FILE_EXTENSIONS)

        env = Environment(
            loader=FileSystemLoader(_collect_template_dirs()) if is_file else DictLoader({"_": template}),
            autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
            enable_async=True,
        )

        # Globals available in every grunt template — mirrors Frappe's Jinja API
        env.globals.update({
            "grunt": self,
            "session": self.session,
            "_": self._,
            "now": datetime.now(timezone.utc),
        })

        tpl = env.get_template(template if is_file else "_")
        return await tpl.render_async(**ctx)


# ── Module-level singleton ────────────────────────────────────────────────────


grunt = GruntApp()


# ── Internal helpers ─────────────────────────────────────────────────────────


def _collect_template_dirs() -> list[str]:
    """Return all Jinja2 template directories in priority order.

    Search order (first match wins in Jinja2 FileSystemLoader):
    1. ``grunt_apps/<app>/templates/``     — user app templates
    2. ``grunt/core/<module>/templates/``  — framework module templates
    """
    dirs: list[str] = []

    # 1. Installed grunt apps
    for pattern in ("grunt_apps/*/templates", "grunt_apps/*/*/templates"):
        for p in sorted(Path(".").glob(pattern)):
            if p.is_dir():
                dirs.append(str(p))

    # 2. All grunt core module template directories
    _core_dir = Path(__file__).parent / "core"
    for p in sorted(_core_dir.rglob("templates")):
        if p.is_dir():
            dirs.append(str(p))

    return dirs


# ── Internal filter helper ────────────────────────────────────────────────────


def _apply_filters(stmt: Any, table: Any, filters: str | dict[str, Any]) -> Any:
    """Apply id/name (str) or operator-aware dict filters to a statement."""
    if isinstance(filters, str):
        stmt = stmt.where((table.c.id == filters) | (table.c.name == filters))
    elif isinstance(filters, dict):
        stmt = _apply_db_filters(stmt, table, filters)
    return stmt


def _format_msgprint(
    msg: str | list,
    *,
    as_list: bool = False,
    as_table: bool = False,
) -> str:
    """Format a msgprint message to an HTML string."""
    if isinstance(msg, str):
        return msg

    if as_table and msg and isinstance(msg[0], (list, tuple)):
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
            for row in msg
        )
        return f"<table>{rows_html}</table>"

    if as_list or isinstance(msg, list):
        items_html = "".join(f"<li>{item}</li>" for item in msg)
        return f"<ul>{items_html}</ul>"

    return str(msg)


_FILTER_OPS = ("__gte", "__lte", "__gt", "__lt", "__like", "__in", "__nin")


def _build_clauses(table: Any, filters: dict[str, Any]) -> list[Any]:
    """Build SQLAlchemy WHERE clauses from a filter dict.

    Supported operator suffixes:
        ``__gte``  → ``>=``
        ``__lte``  → ``<=``
        ``__gt``   → ``>``
        ``__lt``   → ``<``
        ``__like`` → ``LIKE '%value%'``
        ``__in``   → ``IN (value)``   (value must be a list)
        ``__nin``  → ``NOT IN (value)`` (value must be a list)
        (none)     → ``=``
    """
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
    return clauses


def _apply_db_filters(stmt: Any, table: Any, filters: dict[str, Any]) -> Any:
    """Apply AND-filters with operator suffixes to a statement."""
    for clause in _build_clauses(table, filters):
        stmt = stmt.where(clause)
    return stmt
