"""Shared ContextVar storage for Grunt request context.

Both ``grunt.api.context`` and ``grunt.app`` import these objects so that
setting session / engine / user in one place is immediately visible everywhere.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

lazy from grunt.site.manager import site_manager

_session_ctx: ContextVar[AsyncSession | None] = ContextVar("grunt_session", default=None)
_engine_ctx: ContextVar[AsyncEngine | None] = ContextVar("grunt_engine", default=None)
# The ``User`` document the context runs as. Below the auth layer nothing reads
# it as a document: the user is their email (:func:`session_user`) and roles
# (:func:`session_roles`), as in Frappe. ``grunt.get_user()`` hands out the
# document itself (``ContextAPI.get_user`` in ``grunt.app.context_api``).
_user_ctx: ContextVar[Any] = ContextVar("grunt_user", default=None)
_site_ctx: ContextVar[str | None] = ContextVar("grunt_site", default=None)
_messages_ctx: ContextVar[list[dict] | None] = ContextVar("grunt_messages", default=None)
_bootstrap_ctx: ContextVar[bool] = ContextVar("grunt_bootstrap", default=False)


# Context accessors
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

        try:
            return site_manager.get_engine(site_manager.get_active_site())
        except Exception:
            raise RuntimeError("grunt: no active engine.") from None
    return e


def session_user() -> str | None:
    """Email of the user the context runs as; ``None`` without one."""
    user = _user_ctx.get()
    return None if user is None else user.email


def require_session_user() -> str:
    """:func:`session_user`, or raise if no user is bound to the context."""
    email = session_user()
    if email is None:
        raise RuntimeError("grunt: no active user.")
    return email


def session_roles() -> list[str]:
    """Role names of the user the context runs as (``[]`` without one)."""
    user = _user_ctx.get()
    if user is None:
        return []
    rows = getattr(user, "roles", None) or []
    return [r if isinstance(r, str) else r.get("role_name", "") for r in rows]


def clear_context() -> None:
    """Clear all context variables (on request end)."""
    _session_ctx.set(None)
    _user_ctx.set(None)
    _engine_ctx.set(None)
    _site_ctx.set(None)
    _messages_ctx.set(None)


@contextmanager
def bound_session(session: AsyncSession, engine: AsyncEngine) -> Iterator[None]:
    """Bind *session* / *engine* for the block - no user: for framework work that
    reads and writes tables on no one's behalf (metrics, cache invalidation)."""
    tokens = (_session_ctx.set(session), _engine_ctx.set(engine), _user_ctx.set(None))
    try:
        yield
    finally:
        _session_ctx.reset(tokens[0])
        _engine_ctx.reset(tokens[1])
        _user_ctx.reset(tokens[2])
