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

# Module-level Table cache keyed by DocType name.
# Avoids rebuilding Column objects on every call to compile_doctype_to_table().
# Invalidated via invalidate_table_cache() when a DocType is updated or deleted.
_TABLE_CACHE: dict[str, Table] = {}

logger = structlog.get_logger()


def invalidate_table_cache(doctype_name: str) -> None:
    """Remove a cached Table for the given DocType (call on update/delete)."""
    _TABLE_CACHE.pop(doctype_name, None)


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
    UniqueConstraint(
        "parent_doctype",
        "parent_id",
        "parent_field",
        "idx",
        name="uq_grunt_core_multi_link_parent_field_idx",
    ),
    Index(
        "ix_grunt_core_multi_link_parent_parentfield_idx",
        "parent_doctype",
        "parent_id",
        "parent_field",
        "idx",
    ),
    extend_existing=True,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def get_table_name(module: str, doctype_name: str) -> str:
    """Return the physical table name: ``grunt_{module}_{snake_case_name}``."""
    return f"grunt_{module}_{to_snake_case(doctype_name)}"


# ── Type comparison helpers ───────────────────────────────────────────────

# Normalize DB-reported type names to canonical SA type names for comparison.
_TYPE_ALIASES: dict[str, str] = {
    "VARCHAR": "STRING",
    "CHAR": "STRING",
    "BIGINT": "INTEGER",
    "SMALLINT": "INTEGER",
    "TINYINT": "INTEGER",
    "DOUBLE": "FLOAT",
    "REAL": "FLOAT",
    "NUMERIC": "FLOAT",
    "TIMESTAMP": "DATETIME",
}


def _normalize_type(name: str) -> str:
    return _TYPE_ALIASES.get(name.upper(), name.upper())


def _type_changed(desired, current, dialect) -> bool:
    """True if the desired SA type differs from the current DB type."""
    desired_str = _normalize_type(desired.compile(dialect).upper().split("(")[0].strip())
    current_str = _normalize_type(type(current).__name__)
    return desired_str != current_str


def _is_varchar_reduction(desired, current) -> bool:
    """True if both are string types and the desired length is shorter than current."""
    if not isinstance(desired, String):
        return False
    current_len = getattr(current, "length", None)
    desired_len = getattr(desired, "length", None)
    return bool(current_len and desired_len and desired_len < current_len)


# ── Compiler ─────────────────────────────────────────────────────────────


def compile_doctype_to_table(doctype: DocType) -> Table:
    """Convert a :class:`DocType` into a :class:`sqlalchemy.Table`.

    The table includes system columns (``id``, ``name``, ``owner``, timestamps)
    plus one column per physical field.

    Results are cached by DocType name; call :func:`invalidate_table_cache`
    after updating or deleting a DocType so the new definition is picked up.
    """
    cached = _TABLE_CACHE.get(doctype.name)
    # Guard against stale entries: if SA_METADATA no longer holds the Table
    # (e.g. dropped during tests or hot-reload), rebuild and re-cache.
    if cached is not None and cached.name in SA_METADATA.tables:
        return cached

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

    # Per-field unique constraints (named so they can be synced on ALTER)
    constraints: list = []
    for field in doctype.fields:
        if field.unique:
            uq_name = f"uq_{table_name}_{field.fieldname}"
            constraints.append(UniqueConstraint(field.fieldname, name=uq_name))

    # Non-unique indexes
    for field in doctype.fields:
        if field.index and not field.unique:
            constraints.append(Index(f"ix_{table_name}_{field.fieldname}", field.fieldname))

    table = Table(table_name, SA_METADATA, *columns, *constraints, extend_existing=True)
    _TABLE_CACHE[doctype.name] = table
    return table


# ── Sync (create / alter) ───────────────────────────────────────────────


async def sync_table(
    doctype: DocType,
    async_engine: AsyncEngine,
    session: AsyncSession | None = None,
) -> None:
    """Apply DocType changes to the physical database.

    1. Compile DocType → SA Table.
    2. If the table does not exist — ``CREATE TABLE``.
    3. If the table exists:
       - Add missing columns (always as NULL).
       - Alter columns whose type changed (with varchar-reduction safety check).
       - Sync per-field unique constraints (add missing, drop stale).
       - Add missing indexes.
       Columns are **never** dropped.

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
            return

        # ── Columns ────────────────────────────────────────────────────
        existing_col_map = {c["name"]: c["type"] for c in insp.get_columns(table.name)}

        for col in table.columns:
            if col.name not in existing_col_map:
                col_type = col.type.compile(connection.dialect)
                # Always add as NULL to avoid failures on tables with existing rows
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type} NULL')
                )
                logger.info("compiler.column_added", table=table.name, column=col.name)

            elif connection.dialect.name != "sqlite" and _type_changed(
                col.type, existing_col_map[col.name], connection.dialect
            ):
                # Varchar reduction safety: skip if existing data would be truncated
                if _is_varchar_reduction(col.type, existing_col_map[col.name]):
                    max_stored = (
                        connection.execute(
                            text(
                                f'SELECT MAX(char_length("{col.name}")) FROM "{table.name}"'
                                f' WHERE "{col.name}" IS NOT NULL'
                            )
                        ).scalar()
                        or 0
                    )
                    if max_stored > col.type.length:
                        logger.warning(
                            "compiler.skip_varchar_reduction",
                            table=table.name,
                            column=col.name,
                            current_max=max_stored,
                            new_length=col.type.length,
                        )
                        continue

                desired_type = col.type.compile(connection.dialect)
                connection.execute(
                    text(
                        f'ALTER TABLE "{table.name}" ALTER COLUMN "{col.name}" TYPE {desired_type}'
                    )
                )
                logger.info(
                    "compiler.column_altered",
                    table=table.name,
                    column=col.name,
                    new_type=desired_type,
                )

        # ── Unique constraints ──────────────────────────────────────────
        existing_uq = {ix["name"] for ix in insp.get_unique_constraints(table.name)}
        desired_uq = {
            c.name: c
            for c in table.constraints
            if isinstance(c, UniqueConstraint) and c.name
        }
        uq_prefix = f"uq_{table.name}_"

        for name, uq in desired_uq.items():
            if name not in existing_uq:
                cols = ", ".join(f'"{c.name}"' for c in uq.columns)
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD CONSTRAINT "{name}" UNIQUE ({cols})')
                )
                logger.info("compiler.unique_added", table=table.name, constraint=name)

        # Drop stale per-field constraints (those with our naming prefix only)
        for name in existing_uq:
            if name.startswith(uq_prefix) and name not in desired_uq:
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" DROP CONSTRAINT IF EXISTS "{name}"')
                )
                logger.info("compiler.unique_dropped", table=table.name, constraint=name)

        # ── Indexes ────────────────────────────────────────────────────
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
