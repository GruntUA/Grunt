"""Context/session API mixin for GruntApp facade."""

import contextlib
import sys
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.auth.current import acting_user, user_context
from grunt.auth.doctypes.User.user import SYSTEM_USER, User
from grunt.local import (
    _bootstrap_ctx,
    _engine_ctx,
    bind,
    require_session,
    session_user,
    unbind,
)
from grunt.permissions.access_log import record_access


class ContextAPI:
    """Context management and engine/session access helpers for GruntApp."""

    def get_user(self) -> User:
        """The ``User`` document the request or task runs as (401 without one) -
        :func:`grunt.auth.current.acting_user`."""
        return acting_user()

    def set_context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
        user: User | None = None,
    ) -> tuple:
        """Set the request context (session / engine / user).

        Called automatically before invoking lifecycle hooks. Returns a tuple of
        ContextVar tokens that
        can be passed to :meth:`reset_context` to restore the previous state.

        App developers generally do NOT need to call this directly. Without an
        *engine* the one already in context is kept (same site, new session).
        """
        return bind(session, engine, user)

    def reset_context(self, tokens: tuple) -> None:
        """Restore the context to its previous state using tokens from :meth:`set_context`."""
        unbind(tokens)

    @contextlib.asynccontextmanager
    async def context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
        user: User | str | None = None,
    ) -> AsyncGenerator[None]:
        """Run the block as *user* - a ``User`` document or an email - in a
        background task or CLI command (:func:`grunt.auth.current.user_context`)::

            async with grunt.context(session, engine, "jane@example.com"):
                doc = await grunt.get_doc("Invoice", invoice_id)
        """
        async with user_context(session, engine, user):
            yield

    @contextlib.asynccontextmanager
    async def system_context(
        self,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
    ) -> AsyncGenerator[None]:
        """Shortcut for :meth:`context` that runs as the internal SYSTEM_USER.

        Use this in background tasks, hooks, and CLI commands that need to perform
        operations without a real user in scope::

            async with grunt.system_context(session):
                await grunt.new_doc("ActivityLog", {...})

        Without a *session* - the one in context (a hook or a request).
        ``grunt.db`` checks no rights, so it needs no system context.
        """
        async with self.context(
            session if session is not None else require_session(), engine, SYSTEM_USER
        ):
            yield

    @contextlib.asynccontextmanager
    async def sudo(self, reason: str) -> AsyncGenerator[None]:
        """Run the block as the system - for a stated *reason*, recorded.

        The human way to step past permission checks (PERMISSIONS_PLAN step
        7b): ``system_context`` says nothing about who needed it and why;
        ``sudo`` writes an Access Log row (action ``Elevated``) with the user
        the request runs as, the reason and the calling function::

            async with grunt.sudo("count open appeals for the public counter"):
                total = await grunt.db.count("MltAppeal", {"status": "Open"})

        Use it where a user's action needs more than their rights; background
        tasks and bootstrap code without a user keep ``system_context``.
        """
        if not reason or not reason.strip():
            raise ValueError("grunt.sudo needs a reason")
        session = require_session()
        actor = session_user() or ""
        caller = sys._getframe(2)  # the caller's frame (past contextlib)
        where = f"{caller.f_globals.get('__name__', '?')}.{caller.f_code.co_name}"
        await record_access(
            "Elevated", None, reason=f"{reason.strip()} [{where}]", user=actor, session=session
        )
        async with self.system_context(session, _engine_ctx.get()):
            yield

    @contextlib.asynccontextmanager
    async def bootstrap_context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
    ) -> AsyncGenerator[None]:
        """System context with document hooks suppressed during bootstrap."""
        token = _bootstrap_ctx.set(True)
        try:
            async with self.system_context(session, engine):
                yield
        finally:
            _bootstrap_ctx.reset(token)
