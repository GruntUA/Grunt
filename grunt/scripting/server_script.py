"""Server Script engine - execute user-defined Python scripts in a sandbox.

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
import functools
import io
from datetime import UTC
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar

from grunt import log
from grunt.scripting.safe_globals import build_safe_globals, compile_script, validate_script

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from sqlalchemy.ext.asyncio import AsyncSession


_T = TypeVar("_T")

# Maximum execution output capture (bytes)
_MAX_OUTPUT = 10_000
# Maximum script execution time hint (seconds) - enforced externally if needed
MAX_EXEC_SECONDS = 5


class _BufferPrintCollector:
    """RestrictedPython `_print_` collector that writes into an external buffer.

    A script's own `print(...)` statements are compiled to call this (they
    never touch real `sys.stdout`), while `grunt.log(...)` calls real
    `print()` from host code (`ScriptContext.log`, outside the restricted
    compile) - caught separately by `contextlib.redirect_stdout`. Writing
    both into the *same* StringIO keeps script output and grunt.log() output
    in one combined, correctly ordered stream instead of two disjoint ones.
    """

    def __init__(self, buf: io.StringIO, _getattr_: Any = None) -> None:
        self._buf = buf
        self._getattr_ = _getattr_

    def write(self, text: str) -> None:
        self._buf.write(text)

    def __call__(self) -> str:
        return self._buf.getvalue()

    def _call_print(self, *objects: Any, **kwargs: Any) -> None:
        if kwargs.get("file") is None:
            kwargs["file"] = self
        elif self._getattr_ is not None:
            self._getattr_(kwargs["file"], "write")
        print(*objects, **kwargs)


class _SyncBridge:
    """Bridges sync script code back to the async event loop for DB operations."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def run(self, coro: Any) -> Any:
        """Run an async coroutine from synchronous script code."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=MAX_EXEC_SECONDS)


def _bridged[T](fn: Callable[..., Awaitable[T]]) -> Callable[..., T]:
    """Turn an async method into the sync entry point scripts actually call.

    Every ``_DBProxy`` operation needs both a sync surface (RestrictedPython
    scripts run synchronously) and an async implementation (it awaits real DB
    calls) - this collapses each such pair from two named methods (a one-line
    sync trampoline + an ``_async_*`` twin) into one ``async def`` that IS the
    public method, run through ``self._bridge``.
    """

    @functools.wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> T:
        return self._bridge.run(fn(self, *args, **kwargs))

    return wrapper


class _DBProxy:
    """Database helpers exposed as ``grunt.db`` inside scripts."""

    def __init__(self, bridge: _SyncBridge, session: AsyncSession) -> None:
        self._bridge = bridge
        self._session = session

    async def _run_with_session(self, action: Callable[[], Awaitable[_T]]) -> _T:
        from grunt.local import _session_ctx

        token = _session_ctx.set(self._session)
        try:
            return await action()
        finally:
            _session_ctx.reset(token)

    @_bridged
    async def get_value(self, doctype: str, filters: str | dict[str, Any], fieldname: str) -> Any:
        """Get a single field value from a document."""
        from grunt.app import GruntDB

        return await self._run_with_session(
            lambda: GruntDB().get_value(doctype, filters, fieldname)
        )

    @_bridged
    async def set_value(self, doctype: str, doc_id: str, fieldname: str, value: Any) -> None:
        """Update a single field value on a document."""
        from grunt.app import GruntDB

        await self._run_with_session(lambda: GruntDB().set_value(doctype, doc_id, fieldname, value))

    @_bridged
    async def exists(self, doctype: str, filters: str | dict[str, Any]) -> str | None:
        """Return document name if it exists, else None."""
        from grunt.app import GruntDB

        return await self._run_with_session(lambda: GruntDB().exists(doctype, filters))

    @_bridged
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
        """Fetch a list of documents as plain dicts."""
        from grunt.app import GruntDB

        return await self._run_with_session(
            lambda: GruntDB().get_all(
                doctype,
                filters=filters,
                fields=fields,
                limit=limit,
                order_by=order_by,
                order=order,
            )
        )


class _SessionProxy:
    """Session info exposed as ``grunt.session`` inside scripts."""

    def __init__(self, user_email: str = "", roles: list[str] | None = None) -> None:
        self.user = user_email
        self.roles = roles or []

    def has_role(self, *roles: str) -> bool:
        """Return True if the current user has any of the given roles."""
        return bool(set(self.roles).intersection(roles))


class ScriptContext:
    """Helpers injected into server scripts as the ``grunt`` namespace.

    Provides document access, DB operations, session info, and output helpers.
    """

    # Opts this object out of RestrictedPython's full_write_guard wrapping
    # (see Guards._full_write_guard) so restricted scripts can do
    # `grunt.response = {...}` / `grunt.flags[...] = ...` - otherwise every
    # attribute assignment on a host object requires it to implement
    # __guarded_setattr__, which plain Python classes don't have.
    _guarded_writes = True

    def __init__(
        self,
        session: AsyncSession | None = None,
        bridge: _SyncBridge | None = None,
        user_email: str = "",
        user_roles: list[str] | None = None,
    ) -> None:
        self._session = session
        self._bridge = bridge
        self._response: dict[str, Any] = {}
        self._flags: dict[str, Any] = {}
        self.session = _SessionProxy(user_email, roles=user_roles)
        self.db = _DBProxy(bridge, session) if bridge and session else None

    def _get_session(self) -> AsyncSession:
        """Return the session, raising if not set."""
        assert self._session is not None, "No session available in ScriptContext"
        return self._session

    async def _run_with_session(self, action: Callable[[], Awaitable[_T]]) -> _T:
        from grunt.local import _session_ctx

        token = _session_ctx.set(self._get_session())
        try:
            return await action()
        finally:
            _session_ctx.reset(token)

    def _run_or_default(self, coro: Coroutine[Any, Any, _T], default: _T) -> _T:
        """Run *coro* via the bridge, or *default* if there's no bridge/session.

        Missing bridge/session means the context was built for preview/dry-run
        use without a live DB (see ``ScriptContext()`` call sites) - every
        read-only ``grunt.*`` script method degrades to its empty-result
        default in that mode rather than erroring.
        """
        if not self._bridge or not self._session:
            coro.close()  # avoid "coroutine was never awaited"
            return default
        return self._bridge.run(coro)

    def _run_or_raise(self, coro: Coroutine[Any, Any, _T], method_name: str) -> _T:
        """Like ``_run_or_default``, but for mutating methods: no silent no-op."""
        if not self._bridge or not self._session:
            coro.close()
            raise ScriptError(f"{method_name}: no session available")
        return self._bridge.run(coro)

    @property
    def response(self) -> dict[str, Any]:
        return self._response

    @response.setter
    def response(self, value: dict[str, Any]) -> None:
        self._response = value

    @property
    def flags(self) -> dict[str, Any]:
        return self._flags

    def throw(self, msg: str) -> NoReturn:
        """Raise a user-facing error from within a script."""
        raise ScriptError(msg)

    def log(self, *args: Any) -> None:
        """Log a message (visible in script output)."""
        print(*args)

    def get_doc(self, doctype: str, filters_or_id: str | dict[str, Any]) -> dict[str, Any] | None:
        """Fetch a single document by ID/name or filters.

        Usage::

            doc = grunt.get_doc("Applicant", "some-id")
            doc = grunt.get_doc("Applicant", {"tax_id": "1234567890"})
        """
        return self._run_or_default(self._get_doc_impl(doctype, filters_or_id), None)

    async def _get_doc_impl(
        self, doctype: str, filters_or_id: str | dict[str, Any]
    ) -> dict[str, Any] | None:
        from grunt.app import GruntDB

        async def _action() -> dict[str, Any] | None:
            db = GruntDB()
            rows: list[dict[str, Any]]
            if isinstance(filters_or_id, str):
                rows = await db.get_all(doctype, filters={"name": filters_or_id}, limit=1)
            else:
                rows = await db.get_all(doctype, filters=filters_or_id, limit=1)
            return rows[0] if rows else None

        return await self._run_with_session(_action)

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
        return self._run_or_default(self._get_list_impl(doctype, filters, fields, limit), [])

    async def _get_list_impl(
        self,
        doctype: str,
        filters: dict[str, Any] | None,
        fields: list[str] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        from grunt.app import GruntDB

        return await self._run_with_session(
            lambda: GruntDB().get_all(
                doctype,
                filters=filters,
                fields=fields,
                limit=limit,
            )
        )

    def new_doc(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new document and return it.

        Usage::

            inv = grunt.new_doc("Invoice", {"number": "INV-001", "amount": 1500.0})
        """
        return self._run_or_raise(self._new_doc_impl(doctype, data), "new_doc")

    async def _new_doc_impl(self, doctype: str, data: dict[str, Any]) -> dict[str, Any]:
        import grunt

        return await self._run_with_session(lambda: grunt.new_doc(doctype, data))

    def save_doc(self, doctype: str, id_or_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing document.

        Usage::

            updated = grunt.save_doc("Invoice", doc_id, {"status": "Paid"})
        """
        return self._run_or_raise(self._save_doc_impl(doctype, id_or_name, data), "save_doc")

    async def _save_doc_impl(
        self, doctype: str, id_or_name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        from datetime import datetime

        from grunt.app import GruntDB

        async def _action() -> dict[str, Any]:
            update_data = dict(data)
            update_data["modified_at"] = datetime.now(UTC)
            await GruntDB().set_value(doctype, id_or_name, update_data)

            rows = await GruntDB().get_all(doctype, filters={"name": id_or_name}, limit=1)
            return rows[0] if rows else {}

        return await self._run_with_session(_action)

    def delete_doc(self, doctype: str, id_or_name: str) -> None:
        """Delete a document.

        Usage::

            grunt.delete_doc("TempLog", log_id)
        """
        self._run_or_raise(self._delete_doc_impl(doctype, id_or_name), "delete_doc")

    async def _delete_doc_impl(self, doctype: str, id_or_name: str) -> None:
        from grunt.app import GruntDB

        async def _action() -> None:
            deleted = await GruntDB().delete(doctype, {"id": id_or_name})
            if deleted == 0:
                await GruntDB().delete(doctype, {"name": id_or_name})

        await self._run_with_session(_action)

    def count(self, doctype: str, filters: dict[str, Any] | None = None) -> int:
        """Count documents matching optional filters.

        Usage::

            n = grunt.count("Invoice", {"status": "Draft"})
        """
        return self._run_or_default(self._count_impl(doctype, filters), 0)

    async def _count_impl(self, doctype: str, filters: dict[str, Any] | None) -> int:
        from grunt.app import GruntDB

        return await self._run_with_session(lambda: GruntDB().count(doctype, filters=filters))

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
        return self._run_or_default(self._notify_impl(users, subject, message, doctype, doc_id), [])

    async def _notify_impl(
        self,
        users: list[str],
        subject: str,
        message: str,
        doctype: str | None,
        doc_id: str | None,
    ) -> list[str]:
        from grunt.publish import notify as _notify

        return await _notify(
            users=users,
            subject=subject,
            message=message,
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
        from grunt.app import GruntDB
        from grunt.local import _session_ctx

        token = _session_ctx.set(session)
        try:
            rows = await GruntDB().get_all(
                "ServerScript",
                filters={
                    "script_type": "DocType Event",
                    "ref_doctype": doctype,
                    "event": event,
                    "is_enabled": True,
                },
                fields=["name", "script"],
                limit=10_000,
                order_by="name",
                order="asc",
            )
        finally:
            _session_ctx.reset(token)

        scripts: list[dict[str, Any]] = [
            {"name": str(r.get("name") or ""), "script": str(r.get("script") or "")} for r in rows
        ]

        # Append file-based scripts
        try:
            from grunt.scripting.file_scripts import get_file_doctype_scripts

            scripts.extend(get_file_doctype_scripts(doctype, event))
        except ImportError:
            # File-based server scripts are optional; ignore if support module is not available.
            log.debug(
                "Optional file-based DocType scripts module not available; skipping.",
                doctype=doctype,
                doc_event=event,
            )

        return scripts

    async def load_api_script(self, session: AsyncSession, method: str) -> dict[str, Any] | None:
        """Load an API-type server script by method name."""
        from grunt.app import GruntDB
        from grunt.local import _session_ctx

        token = _session_ctx.set(session)
        try:
            rows = await GruntDB().get_all(
                "ServerScript",
                filters={"script_type": "API", "api_method": method, "is_enabled": True},
                fields=["name", "script", "allow_guest"],
                limit=1,
            )
        finally:
            _session_ctx.reset(token)

        row = rows[0] if rows else None
        if row:
            return {
                "name": row.get("name"),
                "script": row.get("script"),
                "allow_guest": row.get("allow_guest"),
            }

        # Check file-based scripts
        try:
            from grunt.scripting.file_scripts import get_file_api_script

            return get_file_api_script(method)
        except ImportError:
            return None

    async def load_scheduler_scripts(self, session: AsyncSession) -> list[dict[str, Any]]:
        """Load all enabled scheduler-type server scripts."""
        from grunt.app import GruntDB
        from grunt.local import _session_ctx

        token = _session_ctx.set(session)
        try:
            rows = await GruntDB().get_all(
                "ServerScript",
                filters={"script_type": "Scheduler Event", "is_enabled": True},
                fields=["name", "script", "cron"],
                limit=10_000,
                order_by="name",
                order="asc",
            )
        finally:
            _session_ctx.reset(token)

        return [
            {"name": r.get("name"), "script": r.get("script"), "cron": r.get("cron")} for r in rows
        ]

    async def execute(
        self,
        source: str,
        doc: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
        extra_context: dict[str, Any] | None = None,
        trusted: bool = False,
        user_email: str = "",
        user_roles: list[str] | None = None,
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

        Returns:
            ScriptResult with success status, captured output, and response data.
        """
        # Friendlier pre-check for untrusted scripts - trusted (file-based)
        # scripts skip straight to the real compile below, which enforces
        # the exact same restrictions either way (see safe_globals.py).
        if not trusted:
            errors = validate_script(source)
            if errors:
                return ScriptResult(
                    success=False,
                    error="; ".join(errors),
                )

        compile_result = compile_script(source)
        if compile_result.errors:
            return ScriptResult(success=False, error="; ".join(compile_result.errors))
        compiled = compile_result.code
        assert compiled is not None  # no errors -> compiled

        # Build execution context with sync-async bridge
        loop = asyncio.get_running_loop()
        bridge = _SyncBridge(loop)
        ctx = ScriptContext(
            session=session,
            bridge=bridge,
            user_email=user_email,
            user_roles=user_roles,
        )
        stdout_buf = io.StringIO()
        script_globals = build_safe_globals(
            extra={
                "doc": doc or {},
                "grunt": ctx,
                # Script's own print(...) statements are routed here by
                # RestrictedPython instead of through the _print_ default
                # (PrintCollector) - see _BufferPrintCollector docstring.
                "_print_": lambda _getattr_=None: _BufferPrintCollector(
                    stdout_buf, _getattr_=_getattr_
                ),
                **(extra_context or {}),
            }
        )

        def _run_script() -> None:
            with contextlib.redirect_stdout(stdout_buf):
                exec(compiled, script_globals)

        try:
            await asyncio.to_thread(_run_script)

            return ScriptResult(
                success=True,
                output=stdout_buf.getvalue()[:_MAX_OUTPUT],
                response=ctx.response,
            )

        except ScriptError as e:
            return ScriptResult(
                success=False,
                output=stdout_buf.getvalue()[:_MAX_OUTPUT],
                error=str(e),
            )
        except Exception as e:
            log.warning(
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
                log.warning(
                    "server_script.event_error",
                    script=s["name"],
                    doctype=doctype,
                    doc_event=event,
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
