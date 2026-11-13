"""Context management for Grunt API - access session/user/engine without passing parameters.

Uses contextvars (defined in grunt.core.context) to store the current session,
user, engine, and site for the duration of each request or task.

So app code reads ``grunt.get_session()`` without passing session/engine
through every call. The user is read as a ``User`` document from
``grunt.get_user()`` (``grunt.app.context_api``) - this module sits below it.
"""

import functools
import inspect as _inspect

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.errors import forbidden
from grunt.local import _engine_ctx, _messages_ctx, _session_ctx, _site_ctx, _user_ctx
from grunt.permissions.roles import has_roles
lazy from grunt.permissions.perms import has_perm
lazy from grunt.site.manager import site_manager


def set_session(session: AsyncSession) -> None:
    """Set the current async session (called by FastAPI dependency or scheduler)."""
    _session_ctx.set(session)


def get_session() -> AsyncSession:
    """Get the current session from context."""
    session = _session_ctx.get()
    if session is None:
        raise RuntimeError(
            "No session in context. "
            "Grunt API must be called from within a request or task with active session."
        )
    return session


def set_engine(engine: AsyncEngine) -> None:
    """Set the current engine."""
    _engine_ctx.set(engine)


def get_engine() -> AsyncEngine:
    """Get the current engine."""
    engine = _engine_ctx.get()
    if engine is None:
        site = get_site()
        engine = site_manager.get_engine(site)
        return engine
    return engine


def set_site(site: str) -> None:
    """Set the current site."""
    _site_ctx.set(site)


def get_site() -> str:
    """Get the current site."""
    site = _site_ctx.get()
    if site is None:
        site = site_manager.get_active_site()
        return site
    return site


def add_message(message: str, title: str = "", msg_type: str = "info") -> None:
    """Append a message to the current request message queue."""
    msgs = _messages_ctx.get()
    if msgs is not None:
        msgs.append({"message": message, "title": title, "type": msg_type})


def whitelist(
    allow_guest: bool = False,
    *,
    roles: list[str] | None = None,
    perm: str | None = None,
    require=None,
    session_cookie: bool = False,
):
    """Decorator to mark a function as whitelisted for API access.

    ``perm`` - a permission the caller must hold (``grunt.permissions.perms``):
    code asks for a capability, an administrator decides which roles have it::

        @grunt.whitelist(perm="grunt.manage_email")
        async def send_test_email(...): ...

    ``roles`` (any of the role names) is the older form apps still use.
    ``perm``/``roles``/``require`` are enforced on every call - via the HTTP dispatcher
    (``api/v1/method.py``) *and* when the function is called directly from
    other Python code (a hook, a test, another whitelisted method) - by reading
    the caller's identity from the active grunt context at call time:

        @grunt.whitelist(
            require=lambda user: user.id == target_id or has_perm("grunt.manage_users")
        )
        async def reset_own_or_admin(...): ...

    A 403 is raised before the function body runs either way - there is no
    call path that skips the check, unlike gating done only in the dispatcher.

    ``session_cookie=True`` lets a GET call without an access token sign in
    with the browser's session cookie - for a read-only method a public site
    page calls (an «Edit» button). Never for a method that changes anything:
    the cookie goes along with requests other sites trigger.
    """

    def _tag(fn, *, allow_guest: bool, roles: list[str] | None, require) -> None:
        fn._whitelisted = True
        fn._allow_guest = allow_guest
        fn._session_cookie = session_cookie
        fn._required_roles = roles
        fn._required_perm = perm
        fn._require_check = require

    def decorator(fn):
        if roles or perm or require is not None:

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                user = _user_ctx.get()  # the User document - ``require`` gets it
                if user is None:
                    raise forbidden()
                if roles and not await has_roles(roles):
                    raise forbidden()
                if perm and not await has_perm(perm):
                    raise forbidden()
                if require is not None:
                    ok = require(user)
                    if _inspect.isawaitable(ok):
                        ok = await ok
                    if not ok:
                        raise forbidden()
                return await fn(*args, **kwargs)

            _tag(wrapper, allow_guest=allow_guest, roles=roles, require=require)
            return wrapper

        _tag(fn, allow_guest=allow_guest, roles=roles, require=require)
        return fn

    # Support both @whitelist and @whitelist()
    if callable(allow_guest):
        fn = allow_guest
        _tag(fn, allow_guest=False, roles=None, require=None)
        return fn

    return decorator


def get_messages() -> list[dict]:
    """Return queued messages for the current request."""
    return _messages_ctx.get() or []


def clear_messages() -> None:
    """Clear the message queue."""
    _messages_ctx.set(None)
