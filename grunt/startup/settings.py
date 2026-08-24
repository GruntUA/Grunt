"""Startup — SystemSettings singleton seeding.

This is a bespoke seeding function for what is otherwise an ordinary
singleton DocType — it could become a ``site/fixtures/SystemSettings.json``
record picked up by the generic ``load_core_fixtures()`` (see
``startup/fixtures.py``), same as every other core seed record. Not yet
folded in because ``load_core_fixtures()`` currently only runs from
``grunt db migrate`` (``cli/db.py``); ``grunt site create`` (``cli/site.py``)
calls this function directly and does not call ``load_core_fixtures()`` at
all, so removing this file would silently stop seeding SystemSettings on
``site create`` unless that call is added there too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

logger = structlog.get_logger()


async def seed_system_settings(session: AsyncSession, engine: AsyncEngine) -> None:
    """Ensure a row exists for the SystemSettings singleton."""
    from grunt.app import grunt

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
