"""Grunt developer API — the primary interface for building apps on the Grunt framework.

This module provides a high-level, async-first API for app developers, similar to
how `frappe` works in the Frappe framework. It is context-aware: the current
database session, engine, and user are automatically injected via ContextVars that
are set by the framework at the start of each request / lifecycle hook call.
"""

from __future__ import annotations

import contextlib
from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog

from grunt.core.context import _engine_ctx, _session_ctx, _user_ctx
from grunt.core.db.profiler import profile
from grunt.core.metadata.registry import doctype_registry
from grunt.db import GruntDB
from grunt.errors import GruntError
from grunt.session import GruntSession
from grunt.utils.app_helpers import _collect_template_dirs, _format_msgprint

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.auth.models import GruntUser
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()


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

    @contextlib.asynccontextmanager
    async def context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
        user: GruntUser | None = None,
    ) -> AsyncGenerator[None, None]:
        """Async context manager that activates a grunt context for background tasks.

        Use this in background tasks and CLI commands instead of calling
        :meth:`set_context` / :meth:`reset_context` directly::

            async with grunt.context(session, engine, SYSTEM_USER):
                doc = await grunt.get_doc("Invoice", invoice_id)
                await doc.submit()
        """
        tokens = self.set_context(session, engine, user)
        try:
            yield
        finally:
            self.reset_context(tokens)

    def _require_session(self) -> AsyncSession:
        s = _session_ctx.get()
        if s is None:
            raise RuntimeError(
                "grunt: no active session — are you inside a request context or lifecycle hook?"
            )
        return s

    def _require_engine(self) -> AsyncEngine:
        e = _engine_ctx.get()
        if e is None:
            # Fallback: get the engine for the active site.
            # This handles internal service calls (auth, email, etc.) that set
            # the context with engine=None because they run outside GruntRouter.
            from grunt.core.site.manager import site_manager  # noqa: PLC0415

            try:
                return site_manager.get_engine(site_manager.get_active_site())
            except Exception:
                raise RuntimeError("grunt: no active engine.") from None
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
        """Fetch a single document by id or name."""
        return await self._svc().get_document(doctype, id_or_name, self._require_user())

    async def new_doc(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new document and return it."""
        return await self._svc().create_document(doctype, data, self._require_user())

    async def save_doc(
        self,
        doctype: str,
        id_or_name: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing document and return the updated version."""
        return await self._svc().update_document(doctype, id_or_name, data, self._require_user())

    async def delete_doc(self, doctype: str, id_or_name: str) -> None:
        """Delete a document."""
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
        """Fetch a list of documents."""
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
        """Create multiple documents in a single database round-trip."""
        import uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415

        from sqlalchemy import insert  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        user = self._require_user()
        session = self._require_session()

        now = datetime.now(UTC)
        rows: list[dict[str, Any]] = []
        ids: list[str] = []

        for rec in records:
            doc_id = str(uuid.uuid4())
            ids.append(doc_id)
            row = {k: v for k, v in rec.items() if k in table.c}
            standard = {
                "id": doc_id,
                "name": rec.get("name") or doc_id,
                "owner": user.email,
                "created_at": now,
                "modified_at": now,
                "modified_by": user.email,
                "docstatus": 0,
            }
            for k, v in standard.items():
                if k in table.c:
                    row[k] = v
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
        """Update multiple documents matching ``filters`` in a single query."""
        from datetime import datetime  # noqa: PLC0415

        from sqlalchemy import update  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        session = self._require_session()
        user = self._require_user()

        update_values = {k: v for k, v in values.items() if k in table.c}
        if "modified_at" in table.c:
            update_values["modified_at"] = datetime.now(UTC).isoformat()
        if "modified_by" in table.c:
            update_values["modified_by"] = user.email

        stmt = update(table).values(**update_values)
        for key, val in filters.items():
            col = table.c.get(key)
            if col is not None:
                stmt = stmt.where(col == val)

        result = await session.execute(stmt)
        await session.flush()
        row_count: int = result.rowcount  # type: ignore[attr-defined]
        logger.info("grunt.bulk_update", doctype=doctype, rows=row_count)
        return row_count

    @profile("grunt.count")
    async def count(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Count documents matching optional filters."""
        return await self.db.count(doctype, filters=filters)

    async def exists(
        self,
        doctype: str,
        filters: dict[str, Any] | str,
    ) -> str | None:
        """Return the document id if a matching record exists, otherwise ``None``.

        Unlike ``grunt.db.exists``, this respects the current user's read permission::

            if await grunt.exists("Invoice", {"number": "INV-001", "status": "Unpaid"}):
                ...
        """
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        user = self._require_user()
        if not await permission_checker.check(user, dt, "read"):
            return None
        return await self.db.exists(doctype, filters)

    async def get_value(
        self,
        doctype: str,
        id_or_name: str,
        fieldname: str,
    ) -> Any:
        """Fetch a single field value from a document.

        Checks read permission and returns ``None`` if the document does not
        exist or the user has no access::

            status = await grunt.get_value("Invoice", invoice_id, "status")
        """
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        user = self._require_user()
        if not await permission_checker.check(user, dt, "read"):
            return None
        return await self.db.get_value(doctype, id_or_name, fieldname)

    async def set_value(
        self,
        doctype: str,
        id_or_name: str,
        fieldname: str | dict[str, Any],
        value: Any = None,
    ) -> None:
        """Update one or more fields directly — lightweight, no lifecycle hooks.

        Checks write permission then issues a single SQL UPDATE.
        Use :meth:`save_doc` when you need ``before_save``/``after_save`` hooks
        to run (e.g. validation, audit log)::

            # single field
            await grunt.set_value("Invoice", invoice_id, "status", "Paid")

            # multiple fields at once
            await grunt.set_value("Invoice", invoice_id, {"status": "Paid", "paid_at": now})
        """
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        await permission_checker.require(self._require_user(), dt, "write")
        await self.db.set_value(doctype, id_or_name, fieldname, value)

    async def get_single(self, doctype: str, fieldname: str) -> Any:
        """Fetch a field value from a Single DocType (singleton document).

        Single DocTypes hold global settings and have no id — they are stored
        as key/value rows rather than regular documents::

            currency = await grunt.get_single("SystemSettings", "default_currency")
        """
        return await self.db.get_single_value(doctype, fieldname)

    async def submit(
        self,
        doctype: str,
        doc_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Apply a workflow transition to a document.

        ``action`` must match a transition label defined in the DocType's workflow.
        Raises ``HTTPException(409)`` if the transition is not available for the
        current document state or the user lacks the required role::

            await grunt.submit("LeaveRequest", request_id, "Approve")
        """
        from grunt.core.workflow.engine import workflow_engine  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        return await workflow_engine.apply_transition(
            dt,
            doc_id,
            action,
            self._require_user(),
            self._require_session(),
            self._require_engine(),
        )

    async def duplicate(
        self,
        doctype: str,
        id_or_name: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a copy of a document and return it.

        Optionally pass ``overrides`` to change specific fields on the copy::

            draft = await grunt.duplicate("Invoice", original_id, overrides={"status": "Draft"})
        """
        original = await self.get_doc(doctype, id_or_name)
        data = {k: v for k, v in original.items() if k not in ("id", "name", "created_at")}
        if overrides:
            data.update(overrides)
        return await self.new_doc(doctype, data)

    async def has_permission(
        self,
        doctype: str,
        action: str,
        doc_id: str | None = None,
    ) -> bool:
        """Check whether the current user has the given permission.

        ``action`` is one of ``"read"``, ``"write"``, ``"create"``, ``"delete"``,
        ``"submit"``::

            if not await grunt.has_permission("Invoice", "delete"):
                grunt.throw("You cannot delete invoices")
        """

        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        user = self._require_user()
        doc: dict[str, Any] | None = None
        if doc_id:
            doc = await self.db.get_value(doctype, doc_id, "*")
        return await permission_checker.check(
            user, dt, action, doc  # type: ignore[arg-type]
        )

    async def enqueue_doc(
        self,
        doctype: str,
        doc_id: str,
        method: str,
        **kwargs: Any,
    ) -> None:
        """Enqueue a controller method to run as a background task.

        The method must exist on the DocType controller and is called with
        ``**kwargs`` in a fresh site context::

            await grunt.enqueue_doc("Report", report_id, "generate", format="pdf")
        """
        from grunt.core.site.manager import site_manager  # noqa: PLC0415
        from grunt.core.tasks.doc_method import enqueue_doc_method  # noqa: PLC0415

        user = self._require_user()
        await enqueue_doc_method(
            site=site_manager.get_active_site(),
            user_email=user.email,
            doctype=doctype,
            doc_id=doc_id,
            method=method,
            kwargs=kwargs,
        )

    # ── Meta ──────────────────────────────────────────────────────────────

    async def get_meta(self, doctype: str) -> DocType:
        """Return the :class:`~grunt.core.metadata.doctype.DocType` definition."""
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
        """Create persistent bell notifications for one or more users."""
        from grunt.publish import notify as _notify  # noqa: PLC0415

        return await _notify(
            users=users,
            subject=subject,
            message=message,
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
        """Send a transient WebSocket message to a specific user (not persisted)."""
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
        """Broadcast a transient WebSocket message to ALL connected users."""
        from grunt.publish import broadcast as _broadcast  # noqa: PLC0415

        await _broadcast(event=event, data=data, message=message, type=type)  # type: ignore[arg-type]

    # ── Error handling ────────────────────────────────────────────────────

    def throw(self, message: str, title: str | None = None) -> None:
        """Raise a user-facing :class:`GruntError`."""
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
        """Show a message dialog to the current user via WebSocket."""
        formatted = _format_msgprint(msg, as_list=as_list, as_table=as_table)

        indicator_to_type = {
            "blue": "info",
            "green": "success",
            "red": "error",
            "orange": "warning",
            "yellow": "warning",
        }
        msg_type = indicator_to_type.get(indicator, "info")

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
        """Render a Jinja2 template and return the result as a string."""
        from datetime import datetime  # noqa: PLC0415

        from jinja2 import (  # noqa: PLC0415
            DictLoader,
            Environment,
            FileSystemLoader,
            select_autoescape,
        )

        ctx = context or {}
        file_extensions = (".html", ".txt", ".md", ".xml", ".jinja", ".j2")
        is_file = any(template.endswith(ext) for ext in file_extensions)

        env = Environment(
            loader=FileSystemLoader(_collect_template_dirs())
            if is_file
            else DictLoader({"_": template}),
            autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
            enable_async=True,
        )

        # Globals available in every grunt template — mirrors Frappe's Jinja API
        env.globals.update(
            {
                "grunt": self,
                "session": self.session,
                "_": self._,
                "now": datetime.now(UTC),
            }
        )

        tpl = env.get_template(template if is_file else "_")
        return await tpl.render_async(**ctx)


# ── Module-level singleton ────────────────────────────────────────────────────


grunt = GruntApp()
