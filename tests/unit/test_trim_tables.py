import pytest
from sqlalchemy import inspect, text

import grunt


@pytest.mark.asyncio
async def test_trim_tables_dry_run(ctx, engine):
    # We will test on 'User' table
    # Add a fake column to the physical table
    user_meta = await grunt.get_meta("User")
    table_name = user_meta.table_name

    async with engine.begin() as conn:
        await conn.execute(
            text(f'ALTER TABLE "{table_name}" ADD COLUMN "fake_col" VARCHAR(255) NULL')
        )

        def _check_col(connection):
            insp = inspect(connection)
            cols = {c["name"] for c in insp.get_columns(table_name)}
            assert "fake_col" in cols

        await conn.run_sync(_check_col)

    # 1. Test dry_run doesn't drop
    # Trim the table using dry-run mode
    await user_meta.trim_table(engine, dry_run=True, quiet=True)

    async with engine.begin() as conn:

        def _check_still_there(connection):
            insp = inspect(connection)
            cols = {c["name"] for c in insp.get_columns(table_name)}
            assert "fake_col" in cols

        await conn.run_sync(_check_still_there)

    # 2. Test actual run drops
    # Trim the table removing the column
    await user_meta.trim_table(engine, dry_run=False, quiet=True)

    async with engine.begin() as conn:

        def _check_dropped(connection):
            insp = inspect(connection)
            cols = {c["name"] for c in insp.get_columns(table_name)}
            assert "fake_col" not in cols

        await conn.run_sync(_check_dropped)
