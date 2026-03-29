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

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()

# ── Per-request context ───────────────────────────────────────────────────────

_session_ctx: ContextVar[AsyncSession | None] = ContextVar("grunt_session", default=None)
_engine_ctx: ContextVar[AsyncEngine | None] = ContextVar("grunt_engine", default=None)
_user_ctx: ContextVar[GruntUser | None] = ContextVar("grunt_user", default=None)


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
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

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
        fieldname: str,
        value: Any,
    ) -> None:
        """Update a single field on a document.

        Args:
            doctype: DocType name.
            doc_id: Document id or name.
            fieldname: Field to update.
            value: New value.
        """
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        await self._session().execute(
            table.update()
            .where((table.c.id == doc_id) | (table.c.name == doc_id))
            .values({fieldname: value})
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
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

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
        fields: list[str] | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Fetch a list of documents as plain dicts.

        Args:
            doctype: DocType name.
            filters: Filter dict, e.g. ``{"status": "Active"}``.
            fields: List of field names to return. Defaults to all fields.
            limit: Maximum number of rows (default 20).
            order_by: Field name to sort by (default: ``modified_at``).
            order: Sort direction — ``"asc"`` or ``"desc"`` (default: ``"desc"``).

        Returns:
            List of dicts.
        """
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)

        if fields:
            cols = [table.c[f] for f in fields if f in table.c]
            stmt = select(*cols) if cols else select(table)
        else:
            stmt = select(table)

        if filters:
            for key, value in filters.items():
                col = table.c.get(key)
                if col is not None:
                    stmt = stmt.where(col == value)

        sort_col = table.c.get(order_by or "modified_at") or table.c.get("created_at")
        if sort_col is not None:
            stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())

        stmt = stmt.limit(limit)
        result = await self._session().execute(stmt)
        return [dict(row._mapping) for row in result.fetchall()]


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
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        svc = DocumentService(self._require_session(), self._require_engine())
        return await svc.get_document(doctype, id_or_name, self._require_user())

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
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        svc = DocumentService(self._require_session(), self._require_engine())
        return await svc.create_document(doctype, data, self._require_user())

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
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        svc = DocumentService(self._require_session(), self._require_engine())
        return await svc.update_document(doctype, id_or_name, data, self._require_user())

    async def delete_doc(self, doctype: str, id_or_name: str) -> None:
        """Delete a document.

        Runs ``before_delete`` and ``after_delete`` hooks.

        Args:
            doctype: DocType name.
            id_or_name: Document id or name.
        """
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        svc = DocumentService(self._require_session(), self._require_engine())
        await svc.delete_document(doctype, id_or_name, self._require_user())

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
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        svc = DocumentService(self._require_session(), self._require_engine())
        result = await svc.list_documents(
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

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

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

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

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
        from sqlalchemy import func, select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        stmt = select(func.count()).select_from(table)
        if filters:
            for key, value in filters.items():
                col = table.c.get(key)
                if col is not None:
                    stmt = stmt.where(col == value)
        result = await self._require_session().execute(stmt)
        return result.scalar() or 0

    # ── Meta ──────────────────────────────────────────────────────────────

    async def get_meta(self, doctype: str) -> DocType:
        """Return the :class:`~grunt.core.metadata.doctype.DocType` definition.

        Args:
            doctype: DocType name.

        Returns:
            DocType pydantic model instance.
        """
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

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

    def log(self, *args: Any) -> None:
        """Log a message via structlog (also captured in server script output)."""
        logger.info("grunt.log", message=" ".join(str(a) for a in args))

    # ── i18n shorthand ────────────────────────────────────────────────────

    def _(self, source: str) -> str:
        """Translate a string using the current request language."""
        from grunt.core.i18n import _ as _translate  # noqa: PLC0415

        return _translate(source)


# ── Module-level singleton ────────────────────────────────────────────────────


grunt = GruntApp()


# ── Internal filter helper ────────────────────────────────────────────────────


def _apply_filters(stmt: Any, table: Any, filters: str | dict[str, Any]) -> Any:
    """Apply id/name or dict filters to a select statement."""
    if isinstance(filters, str):
        stmt = stmt.where((table.c.id == filters) | (table.c.name == filters))
    elif isinstance(filters, dict):
        for k, v in filters.items():
            col = table.c.get(k)
            if col is not None:
                stmt = stmt.where(col == v)
    return stmt
