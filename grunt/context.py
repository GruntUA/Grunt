"""Shared ContextVar storage for Grunt request context.

Both ``grunt.api.context`` and ``grunt.app`` import these objects so that
setting session / engine / user in one place is immediately visible everywhere.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User

_session_ctx: ContextVar[AsyncSession | None] = ContextVar("grunt_session", default=None)
_engine_ctx: ContextVar[AsyncEngine | None] = ContextVar("grunt_engine", default=None)
_user_ctx: ContextVar[User | None] = ContextVar("grunt_user", default=None)
_site_ctx: ContextVar[str | None] = ContextVar("grunt_site", default=None)
_messages_ctx: ContextVar[list[dict] | None] = ContextVar("grunt_messages", default=None)
_bootstrap_ctx: ContextVar[bool] = ContextVar("grunt_bootstrap", default=False)


# ── Context accessors ───────────────────────────────────────────────────────
# Module-level helpers so any layer can read the active request context directly
# (without routing through a GruntApp facade method). The facade keeps thin
# ``_require_*`` method wrappers around these for backward compatibility.


def require_session() -> AsyncSession:
    """Return the active session or raise if none is bound to the context."""
    s = _session_ctx.get()
    if s is None:
        raise RuntimeError(
            "grunt: no active session — are you inside a request context or lifecycle hook?"
        )
    return s


def require_engine() -> AsyncEngine:
    """Return the active engine, falling back to the active site's engine."""
    e = _engine_ctx.get()
    if e is None:
        # Fallback: get the engine for the active site. This handles internal
        # service calls (auth, email, etc.) that set the context with engine=None
        # because they run outside GruntRouter.
        from grunt.site.manager import site_manager

        try:
            return site_manager.get_engine(site_manager.get_active_site())
        except Exception:
            raise RuntimeError("grunt: no active engine.") from None
    return e


def require_user() -> User:
    """Return the active user or raise if none is bound to the context."""
    u = _user_ctx.get()
    if u is None:
        raise RuntimeError("grunt: no active user.")
    return u
