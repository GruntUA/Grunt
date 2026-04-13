import asyncio

from sqlalchemy import select

from grunt.core.db.system_tables import GruntMetaDoctype
from grunt.core.site.manager import site_manager


async def check_db():
    site_name = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site_name)

    async with maker() as session:
        result = await session.execute(
            select(GruntMetaDoctype).where(GruntMetaDoctype.name == "MltMap")
        )
        row = result.scalar_one_or_none()
        if row:
            data = row.data
            print("is_child:", data.get("is_child"))
            print("is_virtual:", data.get("is_virtual"))
            print("module:", data.get("module"))
            print("name:", data.get("name"))
        else:
            print("MltMap NOT found in DB!")

if __name__ == "__main__":
    asyncio.run(check_db())
