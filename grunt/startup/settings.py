"""Startup — SystemSettings singleton seeding."""
#todo: прибрати цей файл взагалі. налаштування - це звичайний доктайп


from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


async def seed_system_settings(session: AsyncSession, engine: AsyncEngine) -> None:
    """Ensure a row exists for the SystemSettings singleton."""
    from grunt.app import grunt  # noqa: PLC0415

    async with grunt.system_context(session, engine):
        if await grunt.db.count("SystemSettings") > 0:
            return

        await grunt.new_doc(
            "SystemSettings",
            {
                "name": "SystemSettings",
                "app_name": "Grunt Framework",
                "language": "uk-UA",
                "timezone": "Europe/Kyiv",
                "date_format": "dd.mm.yyyy",
                "allow_user_registration": False,
            },
        )

    logger.info("startup.system_settings_seeded")
