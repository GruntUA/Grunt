"""The user a request or task runs as, as a ``User`` document - and running as one.

Below the auth layer the user is their email and roles (:func:`grunt.local.session_user`,
:func:`grunt.local.user_email`, :func:`grunt.permissions.roles.get_roles`), as in
Frappe. Code above it - auth, the API, services that act for a user - gets the
document here. ``grunt.get_user`` / ``grunt.context`` are these functions.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.auth.doctypes.User.user import SYSTEM_USER, User, guest_user
from grunt.auth.users import get_auth_context_user
from grunt.errors import ApplicationError
from grunt.i18n import _
from grunt.local import _engine_ctx, _session_ctx, _user_ctx, as_system


def acting_user() -> User:
    """The user the current request or task runs as, as a ``User`` document.

    Never invents one: without a user in context (a guest request, or a task
    that didn't enter ``grunt.context`` / ``grunt.system_context``) it raises a
    401 instead of letting a permission check pass on a stand-in.
    """
    user = _user_ctx.get()
    if user is None:
        raise ApplicationError(_("Authentication required"), code="UNAUTHORIZED")
    return user


async def user_document(
    session: AsyncSession, engine: AsyncEngine | None, user: User | str | None
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
    with as_system(session, engine):
        found = await get_auth_context_user(user)
    if found is None:
        raise LookupError(f"grunt.context: no user {user!r}")
    return found


@asynccontextmanager
async def user_context(
    session: AsyncSession,
    engine: AsyncEngine | None = None,
    user: User | str | None = None,
) -> AsyncIterator[None]:
    """Run the block with *session* / *engine* as *user* - a ``User`` document or
    an email (``grunt.context``)::

        async with user_context(session, engine, "jane@example.com"):
            doc = await documents.get_doc("Invoice", invoice_id)

    Without an *engine* the one already in context is kept (same site, new session).
    """
    doc = await user_document(session, engine, user)
    tokens = (
        _session_ctx.set(session),
        _engine_ctx.set(engine if engine is not None else _engine_ctx.get()),
        _user_ctx.set(doc),
    )
    try:
        yield
    finally:
        _session_ctx.reset(tokens[0])
        _engine_ctx.reset(tokens[1])
        _user_ctx.reset(tokens[2])
