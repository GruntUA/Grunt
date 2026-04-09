"""Server Script engine — execute user-defined Python scripts in a sandbox.

Script types:
- DocType Event: runs on document lifecycle events (before_save, after_insert, etc.)
- API: exposes a custom API endpoint at /api/method/{api_method}
- Scheduler Event: runs on a cron schedule

Scripts have access to a restricted set of builtins + helpers like `doc`, `grunt` namespace.

Available in scripts::

    # Document access
    doc = grunt.get_doc("Applicant", "some-id-or-name")
    docs = grunt.get_list("Applicant", filters={"status": "Active"}, limit=10)
    val = grunt.db.get_value("Applicant", {"tax_id": "1234567890"}, "full_name")
    grunt.db.set_value("Applicant", doc_id, "status", "Verified")

    # Session info
    user = grunt.session.user  # current user email

    # Output
    grunt.response = {"key": "value"}  # return data (API scripts)
    grunt.throw("Error message")       # raise user-facing error
    grunt.log("debug info")            # captured stdout
"""

from __future__ import annotations

import asyncio
import contextlib
import io
from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select
from sqlalchemy import update as sa_update

from grunt.core.scripting.safe_globals import build_safe_globals, validate_script

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Maximum execution output capture (bytes)
_MAX_OUTPUT = 10_000
# Maximum script execution time hint (seconds) — enforced externally if needed
MAX_EXEC_SECONDS = 5


class _SyncBridge:
    """Bridges sync script code back to the async event loop for DB operations."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def run(self, coro: Any) -> Any:
        """Run an async coroutine from synchronous script code."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=MAX_EXEC_SECONDS)


class _DBProxy:
    """Database helpers exposed as ``grunt.db`` inside scripts."""

    def __init__(self, bridge: _SyncBridge, session: AsyncSession) -> None:
        self._bridge = bridge
        self._session = session

    def get_value(self, doctype: str, filters: str | dict[str, Any], fieldname: str) -> Any:
        """Get a single field value from a document."""
        return self._bridge.run(self._async_get_value(doctype, filters, fieldname))

    async def _async_get_value(
        self, doctype: str, filters: str | dict[str, Any], fieldname: str
    ) -> Any:
        from grunt.app import GruntDB  # noqa: PLC0415
        from grunt.core.context import _session_ctx  # noqa: PLC0415

        token = _session_ctx.set(self._session)
        try:
            return await GruntDB().get_value(doctype, filters, fieldname)
        finally:
            _session_ctx.reset(token)

    def set_value(self, doctype: str, doc_id: str, fieldname: str, value: Any) -> None:
        """Update a single field value on a document."""
        self._bridge.run(self._async_set_value(doctype, doc_id, fieldname, value))

    async def _async_set_value(self, doctype: str, doc_id: str, fieldname: str, value: Any) -> None:
        from grunt.app import GruntDB  # noqa: PLC0415
        from grunt.core.context import _session_ctx  # noqa: PLC0415

        token = _session_ctx.set(self._session)
        try:
            await GruntDB().set_value(doctype, doc_id, fieldname, value)
        finally:
            _session_ctx.reset(token)

    def exists(self, doctype: str, filters: str | dict[str, Any]) -> str | None:
        """Return document name if it exists, else None."""
        return self._bridge.run(self._async_exists(doctype, filters))

    async def _async_exists(self, doctype: str, filters: str | dict[str, Any]) -> str | None:
        from grunt.app import GruntDB  # noqa: PLC0415
        from grunt.core.context import _session_ctx  # noqa: PLC0415

        token = _session_ctx.set(self._session)
        try:
            return await GruntDB().exists(doctype, filters)
        finally:
            _session_ctx.reset(token)

    def get_all(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Fetch a list of documents as plain dicts."""
        return self._bridge.run(
            self._async_get_all(doctype, filters, fields, limit, order_by, order)
        )

    async def _async_get_all(
        self,
        doctype: str,
        filters: dict[str, Any] | None,
        fields: list[str] | None,
        limit: int,
        order_by: str | None,
        order: str,
    ) -> list[dict[str, Any]]:
        from grunt.app import GruntDB  # noqa: PLC0415
        from grunt.core.context import _session_ctx  # noqa: PLC0415

        token = _session_ctx.set(self._session)
        try:
            return await GruntDB().get_all(
                doctype, filters=filters, fields=fields, limit=limit, order_by=order_by, order=order
            )
        finally:
            _session_ctx.reset(token)


class _SessionProxy:
    """Session info exposed as ``grunt.session`` inside scripts."""

    def __init__(
        self, user_email: str = "", roles: list[str] | None = None, is_superadmin: bool = False
    ) -> None:
        self.user = user_email
        self.roles = roles or []
        self.is_superadmin = is_superadmin

    def has_role(self, *roles: str) -> bool:
        """Return True if the current user has any of the given roles."""
        return bool(set(self.roles).intersection(roles))


class ScriptContext:
    """Helpers injected into server scripts as the ``grunt`` namespace.

    Provides document access, DB operations, session info, and output helpers.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        bridge: _SyncBridge | None = None,
        user_email: str = "",
        user_roles: list[str] | None = None,
        is_superadmin: bool = False,
    ) -> None:
        self._session = session
        self._bridge = bridge
        self._response: dict[str, Any] = {}
        self._flags: dict[str, Any] = {}
        self.session = _SessionProxy(user_email, roles=user_roles, is_superadmin=is_superadmin)
        self.db = _DBProxy(bridge, session) if bridge and session else None

    def _get_session(self) -> AsyncSession:
        """Return the session, raising if not set."""
        assert self._session is not None, "No session available in ScriptContext"
        return self._session

    @property
    def response(self) -> dict[str, Any]:
        return self._response

    @response.setter
    def response(self, value: dict[str, Any]) -> None:
        self._response = value

    @property
    def flags(self) -> dict[str, Any]:
        return self._flags

    def throw(self, msg: str) -> None:
        """Raise a user-facing error from within a script."""
        raise ScriptError(msg)

    def log(self, *args: Any) -> None:
        """Log a message (visible in script output)."""
        print(*args)  # noqa: T201 — captured by stdout redirect

    def get_doc(self, doctype: str, filters_or_id: str | dict[str, Any]) -> dict[str, Any] | None:
        """Fetch a single document by ID/name or filters.

        Usage::

            doc = grunt.get_doc("Applicant", "some-id")
            doc = grunt.get_doc("Applicant", {"tax_id": "1234567890"})
        """
        if not self._bridge or not self._session:
            return None
        return self._bridge.run(self._async_get_doc(doctype, filters_or_id))

    async def _async_get_doc(
        self, doctype: str, filters_or_id: str | dict[str, Any]
    ) -> dict[str, Any] | None:
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        stmt = select(table)
        if isinstance(filters_or_id, str):
            stmt = stmt.where((table.c.id == filters_or_id) | (table.c.name == filters_or_id))
        elif isinstance(filters_or_id, dict):
            for k, v in filters_or_id.items():
                col = getattr(table.c, k, None)
                if col is not None:
                    stmt = stmt.where(col == v)
        stmt = stmt.limit(1)
        result = await self._get_session().execute(stmt)
        row = result.first()
        if not row:
            return None
        return dict(row._mapping)

    def get_list(
        self,
        doctype: str,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch a list of documents.

        Usage::

            docs = grunt.get_list(
                "Applicant", filters={"applicant_type": "Фізична особа"}, limit=10
            )
        """
        if not self._bridge or not self._session:
            return []
        return self._bridge.run(self._async_get_list(doctype, filters, fields, limit))

    async def _async_get_list(
        self,
        doctype: str,
        filters: dict[str, Any] | None,
        fields: list[str] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)

        if fields:
            cols = [getattr(table.c, f) for f in fields if hasattr(table.c, f)]
            stmt = select(*cols) if cols else select(table)
        else:
            stmt = select(table)

        if filters:
            for k, v in filters.items():
                col = getattr(table.c, k, None)
                if col is not None:
                    stmt = stmt.where(col == v)

        stmt = stmt.limit(limit)
        result = await self._get_session().execute(stmt)
        return [dict(row._mapping) for row in result.fetchall()]

    def new_doc(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new document and return it.

        Usage::

            inv = grunt.new_doc("Invoice", {"number": "INV-001", "amount": 1500.0})
        """
        if not self._bridge or not self._session:
            raise ScriptError("new_doc: no session available")
        return self._bridge.run(self._async_new_doc(doctype, data))

    async def _async_new_doc(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        from grunt.app import grunt as _grunt  # noqa: PLC0415
        from grunt.core.context import _session_ctx  # noqa: PLC0415

        token = _session_ctx.set(self._session)
        try:
            return await _grunt.new_doc(doctype, data)
        finally:
            _session_ctx.reset(token)

    def save_doc(self, doctype: str, id_or_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing document.

        Usage::

            updated = grunt.save_doc("Invoice", doc_id, {"status": "Paid"})
        """
        if not self._bridge or not self._session:
            raise ScriptError("save_doc: no session available")
        return self._bridge.run(self._async_save_doc(doctype, id_or_name, data))

    async def _async_save_doc(
        self, doctype: str, id_or_name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        from datetime import datetime  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        update_data = {k: v for k, v in data.items() if k in table.c}
        update_data["modified_at"] = datetime.now(UTC)
        await self._get_session().execute(
            sa_update(table)
            .where((table.c.id == id_or_name) | (table.c.name == id_or_name))
            .values(**update_data)
        )
        await self._get_session().flush()
        result = await self._get_session().execute(
            select(table).where((table.c.id == id_or_name) | (table.c.name == id_or_name)).limit(1)
        )
        row = result.first()
        return dict(row._mapping) if row else {}

    def delete_doc(self, doctype: str, id_or_name: str) -> None:
        """Delete a document.

        Usage::

            grunt.delete_doc("TempLog", log_id)
        """
        if not self._bridge or not self._session:
            raise ScriptError("delete_doc: no session available")
        self._bridge.run(self._async_delete_doc(doctype, id_or_name))

    async def _async_delete_doc(self, doctype: str, id_or_name: str) -> None:
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        await self._get_session().execute(
            table.delete().where((table.c.id == id_or_name) | (table.c.name == id_or_name))
        )
        await self._get_session().flush()

    def count(self, doctype: str, filters: dict[str, Any] | None = None) -> int:
        """Count documents matching optional filters.

        Usage::

            n = grunt.count("Invoice", {"status": "Draft"})
        """
        if not self._bridge or not self._session:
            return 0
        return self._bridge.run(self._async_count(doctype, filters))

    async def _async_count(self, doctype: str, filters: dict[str, Any] | None) -> int:
        from sqlalchemy import func  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        stmt = select(func.count()).select_from(table)
        if filters:
            for k, v in filters.items():
                col = table.c.get(k)
                if col is not None:
                    stmt = stmt.where(col == v)
        result = await self._get_session().execute(stmt)
        return result.scalar() or 0

    def notify(
        self,
        users: list[str],
        subject: str,
        message: str,
        doctype: str | None = None,
        doc_id: str | None = None,
    ) -> list[str]:
        """Send persistent notifications to users.

        Usage::

            grunt.notify(["user@example.com"], "Order ready", "Your order is ready.")
        """
        if not self._bridge or not self._session:
            return []
        return self._bridge.run(self._async_notify(users, subject, message, doctype, doc_id))

    async def _async_notify(
        self,
        users: list[str],
        subject: str,
        message: str,
        doctype: str | None,
        doc_id: str | None,
    ) -> list[str]:
        from grunt.publish import notify as _notify  # noqa: PLC0415

        return await _notify(
            users=users,
            subject=subject,
            message=message,
            session=self._get_session(),
            doctype=doctype,
            doc_id=doc_id,
        )


class ScriptError(Exception):
    """Error raised by a server script via grunt.throw()."""


class ScriptResult:
    """Result of executing a server script."""

    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str = "",
        response: dict[str, Any] | None = None,
    ) -> None:
        self.success = success
        self.output = output
        self.error = error
        self.response = response or {}


class ServerScriptRunner:
    """Loads and executes server scripts from the database."""

    async def load_doctype_scripts(
        self, session: AsyncSession, doctype: str, event: str
    ) -> list[dict[str, Any]]:
        """Load enabled server scripts for a specific DocType event."""
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["ServerScript"])
        stmt = (
            select(table)
            .where(table.c.script_type == "DocType Event")
            .where(table.c.doctype == doctype)
            .where(table.c.event == event)
            .where(table.c.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()
        scripts: list[dict[str, Any]] = [{"name": r["name"], "script": r["script"]} for r in rows]

        # Append file-based scripts
        try:
            from grunt.core.scripting.file_scripts import get_file_doctype_scripts  # noqa: PLC0415

            scripts.extend(get_file_doctype_scripts(doctype, event))
        except ImportError:
            # File-based server scripts are optional; ignore if support module is not available.
            logger.debug(
                "Optional file-based DocType scripts module not available; skipping.",
                doctype=doctype,
                event=event,
            )

        return scripts

    async def load_api_script(self, session: AsyncSession, method: str) -> dict[str, Any] | None:
        """Load an API-type server script by method name."""
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["ServerScript"])
        stmt = (
            select(table)
            .where(table.c.script_type == "API")
            .where(table.c.api_method == method)
            .where(table.c.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        row = result.mappings().first()
        if row:
            return {
                "name": row["name"],
                "script": row["script"],
                "allow_guest": row["allow_guest"],
            }

        # Check file-based scripts
        try:
            from grunt.core.scripting.file_scripts import get_file_api_script  # noqa: PLC0415

            return get_file_api_script(method)
        except ImportError:
            return None

    async def load_scheduler_scripts(self, session: AsyncSession) -> list[dict[str, Any]]:
        """Load all enabled scheduler-type server scripts."""
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["ServerScript"])
        stmt = (
            select(table)
            .where(table.c.script_type == "Scheduler Event")
            .where(table.c.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()
        return [{"name": r["name"], "script": r["script"], "cron": r["cron"]} for r in rows]

    async def execute(
        self,
        source: str,
        doc: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
        extra_context: dict[str, Any] | None = None,
        trusted: bool = False,
        user_email: str = "",
        user_roles: list[str] | None = None,
        is_superadmin: bool = False,
    ) -> ScriptResult:
        """Execute a server script in a sandboxed environment.

        Args:
            source: Python source code.
            doc: Document data dict (available as ``doc`` in the script).
            session: DB session (available via grunt context).
            extra_context: Additional variables to inject.
            trusted: If True, skip security validation (for file-based app scripts).
            user_email: Current user email for grunt.session.
            user_roles: Roles of the current user for grunt.session.roles.
            is_superadmin: Whether the current user is a superadmin.

        Returns:
            ScriptResult with success status, captured output, and response data.
        """
        # Validate (skip for trusted file-based scripts)
        if not trusted:
            errors = validate_script(source)
            if errors:
                return ScriptResult(
                    success=False,
                    error="; ".join(errors),
                )

        # Build execution context with sync-async bridge
        loop = asyncio.get_running_loop()
        bridge = _SyncBridge(loop)
        ctx = ScriptContext(
            session=session,
            bridge=bridge,
            user_email=user_email,
            user_roles=user_roles,
            is_superadmin=is_superadmin,
        )
        script_globals = build_safe_globals(
            extra={
                "doc": doc or {},
                "grunt": ctx,
                **(extra_context or {}),
            }
        )

        # Capture stdout
        stdout_buf = io.StringIO()
        compiled = compile(source, "<server_script>", "exec")

        def _run_script() -> None:
            with contextlib.redirect_stdout(stdout_buf):
                exec(compiled, script_globals)  # noqa: S102

        try:
            await asyncio.to_thread(_run_script)

            output = stdout_buf.getvalue()[:_MAX_OUTPUT]
            return ScriptResult(
                success=True,
                output=output,
                response=ctx.response,
            )

        except ScriptError as e:
            return ScriptResult(
                success=False,
                output=stdout_buf.getvalue()[:_MAX_OUTPUT],
                error=str(e),
            )
        except Exception as e:
            logger.warning(
                "server_script.error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return ScriptResult(
                success=False,
                output=stdout_buf.getvalue()[:_MAX_OUTPUT],
                error=f"{type(e).__name__}: {e}",
            )

    async def run_doctype_event(
        self,
        session: AsyncSession,
        doctype: str,
        event: str,
        doc: dict[str, Any],
        user_email: str = "",
    ) -> list[ScriptResult]:
        """Load and execute all server scripts for a DocType event."""
        scripts = await self.load_doctype_scripts(session, doctype, event)
        results = []
        for s in scripts:
            result = await self.execute(
                s["script"],
                doc=doc,
                session=session,
                trusted=s.get("trusted", False),
                user_email=user_email,
            )
            if not result.success:
                logger.warning(
                    "server_script.event_error",
                    script=s["name"],
                    doctype=doctype,
                    event=event,
                    error=result.error,
                )
            results.append(result)
        return results

    async def run_api(
        self,
        session: AsyncSession,
        method: str,
        params: dict[str, Any] | None = None,
        user_email: str = "",
    ) -> ScriptResult:
        """Load and execute an API-type server script."""
        script = await self.load_api_script(session, method)
        if not script:
            return ScriptResult(success=False, error=f"API method '{method}' not found")

        return await self.execute(
            script["script"],
            session=session,
            extra_context={"params": params or {}},
            trusted=script.get("trusted", False),
            user_email=user_email,
        )
