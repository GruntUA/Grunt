"""Context/session API mixin for GruntApp facade."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from grunt.context import (
    _bootstrap_ctx,
    _engine_ctx,
    _session_ctx,
    _user_ctx,
    require_engine,
    require_session,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User


class ContextAPI:
    """Context management and engine/session access helpers for GruntApp."""

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
        user: User | None = None,
    ) -> AsyncGenerator[None]:
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

    @contextlib.asynccontextmanager
    async def system_context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
    ) -> AsyncGenerator[None]:
        """Shortcut for :meth:`context` that runs as the internal SYSTEM_USER.

        Use this in background tasks, hooks, and CLI commands that need to perform
        operations without a real user in scope::

            async with grunt.system_context(session):
                await grunt.new_doc("ActivityLog", {...})
        """
        from grunt.auth.doctypes.User.user import SYSTEM_USER

        async with self.context(session, engine, SYSTEM_USER):
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

    def _require_session(self) -> AsyncSession:
        return require_session()

    def _require_engine(self) -> AsyncEngine:
        return require_engine()
