"""DocType Compiler — converts a DocType definition into a SQLAlchemy Table.

Also provides helpers to create / alter the physical table in the database.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    inspect,
    text,
)

from grunt.core.metadata.field import NON_PHYSICAL_FIELDS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.core.metadata.doctype import DocType

import structlog

logger = structlog.get_logger()

# Shared SA MetaData for all dynamically compiled tables
SA_METADATA = MetaData()

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

# ── Field type → SQLAlchemy Column builder ───────────────────────────────

FIELDTYPE_TO_SA: dict[str, object] = {
    "Data": lambda f: Column(f.fieldname, String(f.max_length or 255)),
    "Text": lambda f: Column(f.fieldname, String(f.max_length or 255)),
    "LongText": lambda f: Column(f.fieldname, Text),
    "Int": lambda f: Column(f.fieldname, Integer),
    "Float": lambda f: Column(f.fieldname, Float(precision=6)),
    "Check": lambda f: Column(f.fieldname, Boolean, default=False),
    "Date": lambda f: Column(f.fieldname, Date),
    "Datetime": lambda f: Column(f.fieldname, DateTime(timezone=True)),
    "Time": lambda f: Column(f.fieldname, Time),
    "Select": lambda f: Column(f.fieldname, String(100)),
    "Link": lambda f: Column(f.fieldname, String(255)),
    "Attach": lambda f: Column(f.fieldname, String(500)),
    "Image": lambda f: Column(f.fieldname, String(500)),
    "RichText": lambda f: Column(f.fieldname, Text),
    "JSON": lambda f: Column(f.fieldname, JSON),
    "Color": lambda f: Column(f.fieldname, String(20)),
    "Code": lambda f: Column(f.fieldname, Text),
    "Geolocation": lambda f: Column(f.fieldname, JSON),
    "Signature": lambda f: Column(f.fieldname, Text),
}


# ── Helpers ──────────────────────────────────────────────────────────────


def _to_snake(name: str) -> str:
    """Convert PascalCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def get_table_name(module: str, doctype_name: str) -> str:
    """Return the physical table name: ``grunt_{module}_{snake_case_name}``."""
    return f"grunt_{module}_{_to_snake(doctype_name)}"


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

        builder = FIELDTYPE_TO_SA.get(
            field.fieldtype.value if hasattr(field.fieldtype, "value") else field.fieldtype
        )
        if not builder:
            continue

        col = builder(field)
        col.nullable = True
        # Defaults are handled at the application level (DocumentService),
        # not at the DB column level, to avoid SA compile issues.

        columns.append(col)

    # Unique constraints
    constraints: list[UniqueConstraint] = []
    unique_fields = [f.fieldname for f in doctype.fields if f.unique]
    if unique_fields:
        constraints.append(UniqueConstraint(*unique_fields))

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
                        text(
                            f'ALTER TABLE "{table.name}" '
                            f'ADD COLUMN "{col.name}" {col_type} NULL'
                        )
                    )
                    logger.info(
                        "compiler.column_added",
                        table=table.name,
                        column=col.name,
                    )

    if session is not None:
        conn = await session.connection()
        await conn.run_sync(_sync)
    else:
        async with async_engine.begin() as conn:
            await conn.run_sync(_sync)
