import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

# Add backend to path
sys.path.insert(0, str(Path("backend").resolve()))
sys.path.insert(0, str(Path(".").resolve()))

from sqlalchemy.ext.asyncio import create_async_engine

from grunt.core.db.system_tables import GruntMetaDoctype

# Absolute path to the live DB
DB_URL = "sqlite+aiosqlite:////home/maks4/my-bench/grunt.db"
engine = create_async_engine(DB_URL)

async def dump_appeal():
    async with engine.connect() as conn:
        result = await conn.execute(
            select(GruntMetaDoctype).where(GruntMetaDoctype.name == "Appeal")
        )
        row = result.first()
        if row:
            print(json.dumps(row.data, indent=2, ensure_ascii=False))
        else:
            print("Appeal DocType not found in DB")

if __name__ == "__main__":
    asyncio.run(dump_appeal())
