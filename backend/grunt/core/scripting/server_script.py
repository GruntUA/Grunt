"""Server Script engine — execute user-defined Python scripts in a sandbox.

Script types:
- DocType Event: runs on document lifecycle events (before_save, after_insert, etc.)
- API: exposes a custom API endpoint at /api/method/{api_method}
- Scheduler Event: runs on a cron schedule

Scripts have access to a restricted set of builtins + helpers like `doc`, `grunt` namespace.
"""

from __future__ import annotations

import io
import contextlib
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.scripting.safe_globals import build_safe_globals, validate_script

logger = structlog.get_logger()

# Maximum execution output capture (bytes)
_MAX_OUTPUT = 10_000
# Maximum script execution time hint (seconds) — enforced externally if needed
MAX_EXEC_SECONDS = 5


class ScriptContext:
    """Helpers injected into server scripts as the `grunt` namespace."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session
        self._response: dict[str, Any] = {}
        self._flags: dict[str, Any] = {}

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
        from grunt.core.db.system_tables import GruntServerScript  # noqa: PLC0415

        stmt = (
            select(GruntServerScript)
            .where(GruntServerScript.script_type == "DocType Event")
            .where(GruntServerScript.doctype == doctype)
            .where(GruntServerScript.event == event)
            .where(GruntServerScript.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [{"name": r.name, "script": r.script} for r in rows]

    async def load_api_script(
        self, session: AsyncSession, method: str
    ) -> dict[str, Any] | None:
        """Load an API-type server script by method name."""
        from grunt.core.db.system_tables import GruntServerScript  # noqa: PLC0415

        stmt = (
            select(GruntServerScript)
            .where(GruntServerScript.script_type == "API")
            .where(GruntServerScript.api_method == method)
            .where(GruntServerScript.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            return {
                "name": row.name,
                "script": row.script,
                "allow_guest": row.allow_guest,
            }
        return None

    async def load_scheduler_scripts(
        self, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Load all enabled scheduler-type server scripts."""
        from grunt.core.db.system_tables import GruntServerScript  # noqa: PLC0415

        stmt = (
            select(GruntServerScript)
            .where(GruntServerScript.script_type == "Scheduler Event")
            .where(GruntServerScript.is_enabled.is_(True))
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [{"name": r.name, "script": r.script, "cron": r.cron} for r in rows]

    def execute(
        self,
        source: str,
        doc: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> ScriptResult:
        """Execute a server script in a sandboxed environment.

        Args:
            source: Python source code.
            doc: Document data dict (available as `doc` in the script).
            session: DB session (available via grunt context).
            extra_context: Additional variables to inject.

        Returns:
            ScriptResult with success status, captured output, and response data.
        """
        # Validate
        errors = validate_script(source)
        if errors:
            return ScriptResult(
                success=False,
                error="; ".join(errors),
            )

        # Build execution context
        ctx = ScriptContext(session=session)
        script_globals = build_safe_globals(
            extra={
                "doc": doc or {},
                "grunt": ctx,
                **(extra_context or {}),
            }
        )

        # Capture stdout
        stdout_buf = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_buf):
                exec(compile(source, "<server_script>", "exec"), script_globals)  # noqa: S102

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
    ) -> list[ScriptResult]:
        """Load and execute all server scripts for a DocType event."""
        scripts = await self.load_doctype_scripts(session, doctype, event)
        results = []
        for s in scripts:
            result = self.execute(s["script"], doc=doc, session=session)
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
    ) -> ScriptResult:
        """Load and execute an API-type server script."""
        script = await self.load_api_script(session, method)
        if not script:
            return ScriptResult(success=False, error=f"API method '{method}' not found")

        return self.execute(
            script["script"],
            session=session,
            extra_context={"params": params or {}},
        )
