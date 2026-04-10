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

from grunt.core.context import _engine_ctx, _messages_ctx, _session_ctx, _site_ctx, _user_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.doctypes.user.user import GruntUser


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


def set_user(user: GruntUser) -> None:
    """Set the current user."""
    _user_ctx.set(user)


def get_user() -> GruntUser:
    """Get the current user (may be anonymous for scheduler tasks)."""
    user = _user_ctx.get()
    if user is None:
        from grunt.core.doctypes.user.user import GruntUser as _GruntUser  # noqa: PLC0415

        return _GruntUser(
            id="system",
            email="system",
            full_name="System",
            roles=[],
            is_superadmin=True,
        )
    return user


def set_engine(engine: AsyncEngine) -> None:
    """Set the current engine."""
    _engine_ctx.set(engine)


def get_engine() -> AsyncEngine:
    """Get the current engine."""
    engine = _engine_ctx.get()
    if engine is None:
        from grunt.core.site.manager import site_manager  # noqa: PLC0415

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
        from grunt.core.site.manager import site_manager  # noqa: PLC0415

        site = site_manager.get_active_site()
        return site
    return site


def add_message(message: str, title: str = "", msg_type: str = "info") -> None:
    """Append a message to the current request message queue."""
    msgs = _messages_ctx.get()
    if msgs is not None:
        msgs.append({"message": message, "title": title, "type": msg_type})


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
