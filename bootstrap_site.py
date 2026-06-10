import asyncio

import structlog

from grunt.app import grunt
from grunt.db.base import metadata
from grunt.db.session import async_session_factory, get_engine
from grunt.startup import (
    load_core_doctypes,
    populate_system_doctypes,
    seed_grunt_workspace,
    seed_system_settings,
    sync_all_doctypes,
)

logger = structlog.get_logger()


async def bootstrap():
    logger.info("bootstrap.starting")

    engine = await get_engine()

    # 1. Create all base tables from models
    async with engine.begin() as conn:
        logger.info("bootstrap.create_all_models")
        await conn.run_sync(metadata.create_all)

    # 2. Sync core DocTypes and seed base data
    async with async_session_factory() as session:
        logger.info("bootstrap.loading_core_doctypes")
        await load_core_doctypes(session, sync_db=True)

        logger.info("bootstrap.syncing_doctype_tables")
        await sync_all_doctypes(session, engine)

        logger.info("bootstrap.populating_system_doctypes")
        await populate_system_doctypes(session, engine)

        async with grunt.bootstrap_context(session, engine):
            logger.info("bootstrap.seeding_system_settings")
            await seed_system_settings(session, engine)

            logger.info("bootstrap.seeding_grunt_workspace")
            await seed_grunt_workspace(session, engine)

        await session.commit()

    logger.info("bootstrap.finished")


if __name__ == "__main__":
    asyncio.run(bootstrap())
