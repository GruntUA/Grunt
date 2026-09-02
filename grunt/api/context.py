"""Context management for Grunt API — access session/user/engine without passing parameters.

Uses contextvars (defined in grunt.core.context) to store the current session,
user, engine, and site for the duration of each request or task.

This allows developers to write:
    from grunt import Doc
    doc = await Doc.get("User", "test@mail.com")

Without needing to import and pass session/user/engine everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.context import _engine_ctx, _messages_ctx, _session_ctx, _site_ctx, _user_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User


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


def set_user(user: User) -> None:
    """Set the current user."""
    _user_ctx.set(user)


def get_user() -> User:
    """Get the current user (may be anonymous for scheduler tasks)."""
    user = _user_ctx.get()
    if user is None:
        from grunt.auth.doctypes.User.user import User as _User

        return _User(
            doctype="User",
            data={
                "name": "system",
                "email": "system",
                "full_name": "System",
                "roles": [],
                "is_superadmin": True,
            },
        )
    return user


def set_engine(engine: AsyncEngine) -> None:
    """Set the current engine."""
    _engine_ctx.set(engine)


def get_engine() -> AsyncEngine:
    """Get the current engine."""
    engine = _engine_ctx.get()
    if engine is None:
        from grunt.site.manager import site_manager

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
        from grunt.site.manager import site_manager

        site = site_manager.get_active_site()
        return site
    return site


def add_message(message: str, title: str = "", msg_type: str = "info") -> None:
    """Append a message to the current request message queue."""
    msgs = _messages_ctx.get()
    if msgs is not None:
        msgs.append({"message": message, "title": title, "type": msg_type})


def whitelist(allow_guest: bool = False, *, roles: list[str] | None = None, require=None):
    """Decorator to mark a function as whitelisted for API access.

    ``roles``/``require`` are enforced on every call — via the HTTP dispatcher
    (``api/v1/method.py``) *and* when the function is called directly from
    other Python code (a hook, a test, another whitelisted method) — by reading
    the caller's identity from the active grunt context at call time:

        @grunt.whitelist(roles=["superadmin"])
        async def approve_user_api(user_id: str) -> bool: ...

        @grunt.whitelist(require=lambda user: user.is_superadmin or user.id == target_id)
        async def reset_own_or_admin(...): ...

    A 403 is raised before the function body runs either way — there is no
    call path that skips the check, unlike gating done only in the dispatcher.
    """

    def _tag(fn, *, allow_guest: bool, roles: list[str] | None, require) -> None:
        fn._whitelisted = True
        fn._allow_guest = allow_guest
        fn._required_roles = roles
        fn._require_check = require

    def decorator(fn):
        if roles or require is not None:
            import functools
            import inspect as _inspect

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                from grunt.context import require_user
                from grunt.errors import forbidden
                from grunt.permissions.roles import user_has_roles

                try:
                    user = require_user()
                except RuntimeError:
                    raise forbidden() from None
                if roles and not user_has_roles(user, roles):
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


def clear_context() -> None:
    """Clear all context variables (on request end)."""
    _session_ctx.set(None)
    _user_ctx.set(None)
    _engine_ctx.set(None)
    _site_ctx.set(None)
    _messages_ctx.set(None)
