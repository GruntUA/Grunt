"""Async SQLAlchemy engine and session factory (multi-DB)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.site.manager import site_manager


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a transactional async session for the active site."""
    site_name = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site_name)
    
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_engine() -> AsyncEngine:
    """FastAPI dependency that yields the engine for the active site."""
    site_name = site_manager.get_active_site()
    return site_manager.get_engine(site_name)
