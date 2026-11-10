"""Context/session API mixin for GruntApp facade."""

import contextlib
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.auth.doctypes.User.user import SYSTEM_USER, User, guest_user
from grunt.errors import ApplicationError
from grunt.i18n import _
from grunt.local import (
    _bootstrap_ctx,
    _engine_ctx,
    _session_ctx,
    _user_ctx,
)
lazy from grunt.auth.users import get_auth_context_user


class ContextAPI:
    """Context management and engine/session access helpers for GruntApp."""

    def get_user(self) -> User:
        """The user the current request or task runs as, as a ``User`` document.

        Below the auth layer the user is their email and roles
        (:func:`grunt.local.session_user`, :func:`grunt.permissions.roles.get_roles`),
        as in Frappe; code above it - auth, the API, apps - gets the document here.

        Never invents one: without a user in context (a guest request, or a task
        that didn't enter ``grunt.context`` / ``grunt.system_context``) it raises
        a 401 instead of letting a permission check pass on a stand-in.
        """
        user = _user_ctx.get()
        if user is None:
            raise ApplicationError(_("Authentication required"), code="UNAUTHORIZED")
        return user

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
        return (
            _session_ctx.set(session),
            _engine_ctx.set(engine if engine is not None else _engine_ctx.get()),
            _user_ctx.set(user),
        )

    def reset_context(self, tokens: tuple) -> None:
        """Restore the context to its previous state using tokens from :meth:`set_context`."""
        _session_ctx.reset(tokens[0])
        _engine_ctx.reset(tokens[1])
        _user_ctx.reset(tokens[2])

    async def _user_document(
        self, session: AsyncSession, engine: AsyncEngine | None, user: User | str | None
    ) -> User | None:
        """*user* as a ``User`` document - an email is looked up (as ``frappe.set_user``)."""
        if not isinstance(user, str):
            return user
        current = _user_ctx.get()
        if current is not None and current.email == user:
            return current
        if user == SYSTEM_USER_EMAIL:
            return SYSTEM_USER
        if user == GUEST_USER_EMAIL:
            return guest_user()
        tokens = self.set_context(session, engine, SYSTEM_USER)
        try:
            found = await get_auth_context_user(user)
        finally:
            self.reset_context(tokens)
        if found is None:
            raise LookupError(f"grunt.context: no user {user!r}")
        return found

    @contextlib.asynccontextmanager
    async def context(
        self,
        session: AsyncSession,
        engine: AsyncEngine | None = None,
        user: User | str | None = None,
    ) -> AsyncGenerator[None]:
        """Async context manager that activates a grunt context for background tasks.

        Use this in background tasks and CLI commands instead of calling
        :meth:`set_context` / :meth:`reset_context` directly::

            async with grunt.context(session, engine, "jane@example.com"):
                doc = await grunt.get_doc("Invoice", invoice_id)
                await doc.submit()

        *user* - a ``User`` document or an email (code below the auth layer
        knows users by email only).
        """
        doc = await self._user_document(session, engine, user)
        tokens = self.set_context(session, engine, doc)
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
