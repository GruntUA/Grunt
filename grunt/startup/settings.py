"""Startup - SystemSettings singleton seeding.

This is a bespoke seeding function for what is otherwise an ordinary
singleton DocType - it could become a ``site/fixtures/SystemSettings.json``
record picked up by the generic ``load_core_fixtures()`` (see
``startup/fixtures.py``), same as every other core seed record. Not yet
folded in because ``load_core_fixtures()`` currently only runs from
``grunt migrate`` (``cli/db.py``); ``grunt site create`` (``cli/site.py``)
calls this function directly and does not call ``load_core_fixtures()`` at
all, so removing this file would silently stop seeding SystemSettings on
``site create`` unless that call is added there too.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.db.api import GruntDB
from grunt.local import system_context
from grunt.log import log
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session


async def seed_system_settings(session: AsyncSession, engine: AsyncEngine) -> None:
    """Ensure a row exists for the SystemSettings singleton."""
    async with system_context(session, engine):
        if await _db.count("SystemSettings") > 0:
            return

        await documents.new_doc(
            "SystemSettings",
            {
                "name": "SystemSettings",
                "app_name": "Grunt Framework",
                "language": "uk",
                "timezone": "Europe/Kyiv",
                "date_format": "dd.mm.yyyy",
                "allow_user_registration": False,
            },
        )

    log.info("startup.system_settings_seeded")
