"""Context/session API mixin for GruntApp facade."""

import contextlib
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.auth.current import acting_user, user_context
from grunt.auth.doctypes.User.user import SYSTEM_USER, User
from grunt.local import (
    _bootstrap_ctx,
    bind,
    unbind,
)


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
        session: AsyncSession,
        engine: AsyncEngine | None = None,
    ) -> AsyncGenerator[None]:
        """Shortcut for :meth:`context` that runs as the internal SYSTEM_USER.

        Use this in background tasks, hooks, and CLI commands that need to perform
        operations without a real user in scope::

            async with grunt.system_context(session):
                await grunt.new_doc("ActivityLog", {...})
        """
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
