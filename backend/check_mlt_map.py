import asyncio

from grunt.app import grunt
from grunt.core.metadata.registry import doctype_registry


async def check_mlt_map():
    await grunt.init()
    all_dts = await doctype_registry.list_all()
    found = [dt.name for dt in all_dts if dt.name == "MltMap"]
    print(f"Found MltMap: {found}")
    
    # Also check if it's child or virtual
    if found:
        dt = await doctype_registry.get("MltMap")
        print(f"Is Child: {dt.is_child}")
        print(f"Is Virtual: {dt.is_virtual}")

if __name__ == "__main__":
    asyncio.run(check_mlt_map())
