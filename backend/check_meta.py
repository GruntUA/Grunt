import asyncio
import json
from sqlalchemy import text
from grunt.core.site.manager import site_manager, current_site

async def check_metadata(site_name: str):
    token = current_site.set(site_name)
    try:
        engine = site_manager.get_engine(site_name)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT data FROM grunt_meta_doctype WHERE name = 'SystemSettings'"))
            row = res.fetchone()
            if row:
                data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                fields = data.get('fields', [])
                print(f"DocType Label: {data.get('label')}")
                print(f"Metadata Fields ({len(fields)}):")
                for f in fields:
                    print(f" - {f.get('fieldname')}: {f.get('fieldtype')} ({f.get('label')})")
            else:
                print("SystemSettings not found in grunt_meta_doctype")
    finally:
        current_site.reset(token)

if __name__ == "__main__":
    asyncio.run(check_metadata("dev.local"))
