"""Async SQLAlchemy engine and session factory (multi-DB)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from grunt import log
from grunt.site.manager import site_manager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def _bind_session_context(session: AsyncSession) -> None:
    """Set *session* in the Grunt API context (lazy import to avoid cycles)."""
    try:
        from grunt.api.context import set_session as _set

        _set(session)
    except ImportError:
        log.debug("suppressed_expected_error", exc_info=True)


def _clear_session_context() -> None:
    try:
        from grunt.api.context import clear_context as _clear

        _clear()
    except ImportError:
        log.debug("suppressed_expected_error", exc_info=True)


@asynccontextmanager
async def _session_scope() -> AsyncGenerator[AsyncSession]:
    """Open a session for the active site, bound to the Grunt API context.

    Shared by ``get_session`` (FastAPI dependency) and ``async_session_factory``
    (everywhere else) — the two differ only in *how* they're invoked, not in
    session lifecycle: bind → yield → commit/rollback → unbind.
    """
    site_name = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site_name)

    async with maker() as session:
        try:
            _bind_session_context(session)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _clear_session_context()


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields a transactional async session for the active site.

    Also sets the session in the Grunt API context so developers can use:
        import grunt
        doc = await grunt.get_doc(...)
    """
    async with _session_scope() as session:
        yield session


async def get_engine() -> AsyncEngine:
    """FastAPI dependency that yields the engine for the active site."""
    site_name = site_manager.get_active_site()
    engine = site_manager.get_engine(site_name)

    # Also set in context (lazy import)
    try:
        from grunt.api.context import set_engine as _set

        _set(engine)
    except ImportError:
        log.debug("suppressed_expected_error", exc_info=True)

    return engine


def async_session_factory() -> AbstractAsyncContextManager[AsyncSession]:
    """Context manager for acquiring a session outside of a FastAPI request.

    Use in background tasks, scheduler jobs, and CLI commands where there is
    no active HTTP request to inject dependencies.

    Example::

        async with async_session_factory() as session:
            ...
    """
    return _session_scope()
