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

    # System columns are kept — only fake_col is reported.
    async with engine.begin() as conn:
        db_cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns(table_name)}
        )
    assert db_cols - set(user_meta.get_valid_columns()) == {"fake_col"}

    # 2. Test actual run drops
    # Trim the table removing the column
    await user_meta.trim_table(engine, dry_run=False, quiet=True)

    async with engine.begin() as conn:

        def _check_dropped(connection):
            insp = inspect(connection)
            cols = {c["name"] for c in insp.get_columns(table_name)}
            assert "fake_col" not in cols

        await conn.run_sync(_check_dropped)


@pytest.mark.asyncio
async def test_valid_columns_include_system_columns(ctx):
    """Trimming must never drop the compiler's system columns (modified_by, child links)."""
    user = set((await grunt.get_meta("User")).get_valid_columns())
    assert {"name", "owner", "created_at", "modified_at", "modified_by"} <= user

    child = set((await grunt.get_meta("UserRole")).get_valid_columns())
    assert {"parent_name", "parent_doctype", "parent_field", "idx"} <= child


@pytest.mark.asyncio
async def test_trim_keeps_columns_of_doctypes_sharing_the_table(ctx, engine):
    """``keep`` — another DocType on the same table_name still defines the column."""
    meta = await grunt.get_meta("User")
    table_name = meta.table_name
    async with engine.begin() as conn:
        await conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "shared_col" TEXT'))

    await meta.trim_table(engine, quiet=True, keep={"shared_col"})

    async with engine.begin() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns(table_name)}
        )
    assert "shared_col" in cols
