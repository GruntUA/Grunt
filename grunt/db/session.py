"""Async SQLAlchemy engine and session factory (multi-DB)."""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.local import _engine_ctx, _session_ctx, clear_context
from grunt.site.manager import site_manager


def _bind_session_context(session: AsyncSession) -> None:
    """Set *session* in the Grunt context."""
    _session_ctx.set(session)


def _clear_session_context() -> None:
    clear_context()


@asynccontextmanager
async def _session_scope() -> AsyncGenerator[AsyncSession]:
    """Open a session for the active site, bound to the Grunt API context.

    Shared by ``get_session`` (FastAPI dependency) and ``async_session_factory``
    (everywhere else) - the two differ only in *how* they're invoked, not in
    session lifecycle: bind -> yield -> commit/rollback -> unbind.
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

    _engine_ctx.set(engine)  # also in the Grunt context

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
