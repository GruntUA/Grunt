import asyncio
import json
from pathlib import Path
from grunt.core.metadata.registry import doctype_registry
from grunt.core.metadata.doctype import DocType
from grunt.core.startup import load_core_doctypes, seed_system_settings, populate_system_doctypes
from grunt.core.site.manager import site_manager, current_site
from sqlalchemy import update
from grunt.core.db.system_tables import GruntMetaDoctype

async def force_sync_system_settings(site_name: str):
    print(f"Force syncing SystemSettings for site: {site_name}")
    token = current_site.set(site_name)
    try:
        engine = site_manager.get_engine(site_name)
        maker = site_manager.get_session_maker(site_name)
        
        # Load the JSON file
        json_path = Path("grunt/core/doctypes/SystemSettings.json")
        with open(json_path, "r", encoding="utf-8") as f:
            dt_data = json.load(f)
            dt_obj = DocType.model_validate(dt_data)
        
        async with maker() as session:
            # Manually update the DB row to match JSON
            await session.execute(
                update(GruntMetaDoctype)
                .where(GruntMetaDoctype.name == "SystemSettings")
                .values(data=dt_obj.model_dump())
            )
            await session.commit()
            print("Successfully force-updated SystemSettings metadata in DB")
            
            # Now run the normal sync to ensure table is OK
            await load_core_doctypes(session, engine)
            await seed_system_settings(session, engine)
            await session.commit()
            print("Completed full sync")
    finally:
        current_site.reset(token)

if __name__ == "__main__":
    asyncio.run(force_sync_system_settings("dev.local"))
