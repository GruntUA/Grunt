"""Context management for Grunt API — access session/user/engine without passing parameters.

Uses contextvars to store:
- Current session (AsyncSession)
- Current user (GruntUser)
- Current engine (AsyncEngine)
- Current site

This allows developers to write:
    from grunt import Doc
    doc = await Doc.get("User", "test@mail.com")

Without needing to import and pass session/user/engine everywhere.
"""

from contextvars import ContextVar
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.models import GruntUser

# Context variables (per-request or per-task)
_session_var: ContextVar[Optional[AsyncSession]] = ContextVar("grunt_session", default=None)
_user_var: ContextVar[Optional[GruntUser]] = ContextVar("grunt_user", default=None)
_engine_var: ContextVar[Optional[AsyncEngine]] = ContextVar("grunt_engine", default=None)
_site_var: ContextVar[Optional[str]] = ContextVar("grunt_site", default=None)


def set_session(session: AsyncSession) -> None:
    """Set the current async session (called by FastAPI dependency or scheduler)."""
    _session_var.set(session)


def get_session() -> AsyncSession:
    """Get the current session from context."""
    session = _session_var.get()
    if session is None:
        raise RuntimeError(
            "No session in context. "
            "Grunt API must be called from within a request or task with active session. "
            "Use: async with grunt.api.set_session_context(session, user, engine) as ctx:"
        )
    return session


def set_user(user: GruntUser) -> None:
    """Set the current user."""
    _user_var.set(user)


def get_user() -> GruntUser:
    """Get the current user (may be anonymous for scheduler tasks)."""
    user = _user_var.get()
    if user is None:
        # Return a system user (for scheduler tasks)
        from grunt.core.auth.models import GruntUser as _GruntUser

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
    _engine_var.set(engine)


def get_engine() -> AsyncEngine:
    """Get the current engine."""
    engine = _engine_var.get()
    if engine is None:
        from grunt.core.site.manager import site_manager

        site = get_site()
        engine = site_manager.get_engine(site)
        return engine
    return engine


def set_site(site: str) -> None:
    """Set the current site."""
    _site_var.set(site)


def get_site() -> str:
    """Get the current site."""
    site = _site_var.get()
    if site is None:
        from grunt.core.site.manager import site_manager

        site = site_manager.get_active_site()
        return site
    return site


def clear_context() -> None:
    """Clear all context variables (on request end)."""
    _session_var.set(None)
    _user_var.set(None)
    _engine_var.set(None)
    _site_var.set(None)
