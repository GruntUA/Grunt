import asyncio

import grunt
from grunt import log
from grunt.db.session import async_session_factory, get_engine
from grunt.startup import (
    load_core_doctypes,
    seed_grunt_workspace,
    seed_system_settings,
    sync_all_doctypes,
)


async def bootstrap():
    log.info("bootstrap.starting")

    engine = await get_engine()

    # Sync core DocTypes and seed base data
    async with async_session_factory() as session:
        log.info("bootstrap.loading_core_doctypes")
        await load_core_doctypes(session, sync_db=True)

        log.info("bootstrap.syncing_doctype_tables")
        await sync_all_doctypes(session, engine)

        async with grunt.bootstrap_context(session, engine):
            log.info("bootstrap.seeding_system_settings")
            await seed_system_settings(session, engine)

            log.info("bootstrap.seeding_grunt_workspace")
            await seed_grunt_workspace(session, engine)

        await session.commit()

    log.info("bootstrap.finished")


if __name__ == "__main__":
    asyncio.run(bootstrap())
