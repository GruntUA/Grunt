import asyncio

import structlog

from grunt.core.db.base import Base
from grunt.core.db.session import async_session_factory, get_engine
from grunt.core.startup import (
    load_core_doctypes,
    populate_system_doctypes,
    seed_grunt_workspace,
    seed_system_settings,
)

logger = structlog.get_logger()

async def bootstrap():
    logger.info("bootstrap.starting")
    
    engine = await get_engine()
    
    # 1. Create all base tables from models
    async with engine.begin() as conn:
        logger.info("bootstrap.create_all_models")
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Sync core DocTypes and seed base data
    async with async_session_factory() as session:
        logger.info("bootstrap.loading_core_doctypes")
        await load_core_doctypes(session, engine)
        
        logger.info("bootstrap.populating_system_doctypes")
        await populate_system_doctypes(session, engine)
        
        logger.info("bootstrap.seeding_system_settings")
        await seed_system_settings(session, engine)
        
        logger.info("bootstrap.seeding_grunt_workspace")
        await seed_grunt_workspace(session)
        
        await session.commit()
    
    logger.info("bootstrap.finished")

if __name__ == "__main__":
    asyncio.run(bootstrap())
