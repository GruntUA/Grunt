"""Async SQLAlchemy engine and session factory (multi-DB)."""

from __future__ import annotations

import structlog
logger = structlog.get_logger()
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from grunt.site.manager import site_manager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields a transactional async session for the active site.

    Also sets the session in the Grunt API context so developers can use:
        from grunt.app import grunt
        doc = await grunt.get_doc(...)
    """
    site_name = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site_name)

    async with maker() as session:
        try:
            # Set session in Grunt API context (lazy import to avoid cycles)
            try:
                from grunt.api.context import set_session as _set  # noqa: PLC0415

                _set(session)
            except ImportError:
                logger.debug("suppressed_expected_error", exc_info=True)

            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Clear session from context
            try:
                from grunt.api.context import clear_context as _clear  # noqa: PLC0415

                _clear()
            except ImportError:
                logger.debug("suppressed_expected_error", exc_info=True)


async def get_engine() -> AsyncEngine:
    """FastAPI dependency that yields the engine for the active site."""
    site_name = site_manager.get_active_site()
    engine = site_manager.get_engine(site_name)

    # Also set in context (lazy import)
    try:
        from grunt.api.context import set_engine as _set  # noqa: PLC0415

        _set(engine)
    except ImportError:
        logger.debug("suppressed_expected_error", exc_info=True)

    return engine


@asynccontextmanager
async def async_session_factory() -> AsyncGenerator[AsyncSession]:
    """Context manager for acquiring a session outside of a FastAPI request.

    Use in background tasks, scheduler jobs, and CLI commands where there is
    no active HTTP request to inject dependencies.

    Example::

        async with async_session_factory() as session:
            ...
    """
    site_name = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site_name)
    async with maker() as session:
        try:
            # Set in context for Grunt API (lazy import)
            try:
                from grunt.api.context import set_session as _set  # noqa: PLC0415

                _set(session)
            except ImportError:
                logger.debug("suppressed_expected_error", exc_info=True)

            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            try:
                from grunt.api.context import clear_context as _clear  # noqa: PLC0415

                _clear()
            except ImportError:
                logger.debug("suppressed_expected_error", exc_info=True)
