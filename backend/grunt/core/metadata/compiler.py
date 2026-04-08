from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    inspect,
    text,
)

from grunt.core.metadata.field import NON_PHYSICAL_FIELDS
from grunt.utils.strings import to_snake_case

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.metadata.doctype import DocType


# Shared SA MetaData for all dynamically compiled tables
SA_METADATA = MetaData()

logger = structlog.get_logger()
# ── MultiLink junction table ─────────────────────────────────────────────

MULTI_LINK_TABLE = Table(
    "grunt_core_multi_link",
    SA_METADATA,
    Column("id", String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("parent_doctype", String(255), nullable=False),
    Column("parent_id", String(36), nullable=False),
    Column("parent_field", String(255), nullable=False),
    Column("link_doctype", String(255), nullable=False),
    Column("link_name", String(255), nullable=False),
    Column("idx", Integer, default=0),
    extend_existing=True,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def get_table_name(module: str, doctype_name: str) -> str:
    """Return the physical table name: ``grunt_{module}_{snake_case_name}``."""
    return f"grunt_{module}_{to_snake_case(doctype_name)}"


# ── Compiler ─────────────────────────────────────────────────────────────


def compile_doctype_to_table(doctype: DocType) -> Table:
    """Convert a :class:`DocType` into a :class:`sqlalchemy.Table`.

    The table includes system columns (``id``, ``name``, ``owner``, timestamps)
    plus one column per physical field.
    """
    table_name = doctype.table_name or get_table_name(doctype.module, doctype.name)

    columns: list[Column] = [
        Column("id", String(36), primary_key=True, default=lambda: str(uuid.uuid4())),
        Column("name", String(255), nullable=False),
        Column("owner", String(255), nullable=False),
        Column("created_at", DateTime(timezone=True)),
        Column("modified_at", DateTime(timezone=True)),
        Column("modified_by", String(255)),
        Column("docstatus", Integer, default=0),
    ]

    # Workflow state column
    if doctype.workflow:
        columns.append(Column(doctype.workflow.state_field, String(100)))

    # Child-table specific columns
    if doctype.is_child:
        columns.extend(
            [
                Column("parent_id", String(36), nullable=False),
                Column("parent_doctype", String(255), nullable=False),
                Column("parent_field", String(255), nullable=False),
                Column("idx", Integer, default=0),
            ]
        )

    # User-defined fields
    for field in doctype.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue

        try:
            col = field.to_sa_column()
        except ValueError:
            # Non-physical or unknown type — skip silently
            continue

        col.nullable = True
        # Defaults are handled at the application level (DocumentService),
        # not at the DB column level, to avoid SA compile issues.

        columns.append(col)

    # Unique constraints
    constraints: list = []
    unique_fields = [f.fieldname for f in doctype.fields if f.unique]
    if unique_fields:
        constraints.append(UniqueConstraint(*unique_fields))

    # Non-unique indexes
    for field in doctype.fields:
        if field.index and not field.unique:
            constraints.append(Index(f"ix_{table_name}_{field.fieldname}", field.fieldname))

    return Table(table_name, SA_METADATA, *columns, *constraints, extend_existing=True)


# ── Sync (create / alter) ───────────────────────────────────────────────


async def sync_table(
    doctype: DocType,
    async_engine: AsyncEngine,
    session: AsyncSession | None = None,
) -> None:
    """Apply DocType changes to the physical database.

    1. Compile DocType → SA Table.
    2. If the table does not exist — ``CREATE TABLE``.
    3. If the table exists — compare columns and ``ALTER TABLE ADD COLUMN``
       for any new ones.  Columns are **never** dropped.

    When *session* is provided, uses its underlying connection instead of
    opening a new one (avoids SQLite "database is locked" errors).
    """
    if doctype.is_virtual:
        logger.debug("compiler.skip_virtual", doctype=doctype.name)
        return

    table = compile_doctype_to_table(doctype)

    def _sync(connection):  # noqa: ANN001 — runs inside run_sync
        insp = inspect(connection)
        if not insp.has_table(table.name):
            SA_METADATA.create_all(connection, tables=[table])
            logger.info("compiler.table_created", table=table.name)
        else:
            existing_cols = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing_cols:
                    col_type = col.type.compile(connection.dialect)
                    # Always add as NULL to avoid failures on tables with existing rows
                    connection.execute(
                        text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type} NULL')
                    )
                    logger.info(
                        "compiler.column_added",
                        table=table.name,
                        column=col.name,
                    )

            # Apply any new indexes that don't exist yet
            existing_indexes = {ix["name"] for ix in insp.get_indexes(table.name)}
            for index in table.indexes:
                if index.name and index.name not in existing_indexes:
                    index.create(connection)
                    logger.info("compiler.index_created", table=table.name, index=index.name)

    if session is not None:
        conn = await session.connection()
        await conn.run_sync(_sync)
    else:
        async with async_engine.begin() as conn:
            await conn.run_sync(_sync)
