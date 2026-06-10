from __future__ import annotations

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

from grunt.metadata.field import NON_PHYSICAL_FIELDS
from grunt.utils.strings import to_snake_case

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.metadata.doctype import DocType


# Shared SA MetaData for all dynamically compiled tables
SA_METADATA = MetaData()

# Module-level Table cache keyed by DocType name.
# Avoids rebuilding Column objects on every call to compile_doctype_to_table().
# Invalidated via invalidate_table_cache() when a DocType is updated or deleted.
_TABLE_CACHE: dict[str, Table] = {}

logger = structlog.get_logger()


class DuplicateDataError(Exception):
    """Raised when a unique constraint cannot be added due to duplicate values.

    Attributes:
        table      — physical table name
        constraint — constraint/index name
        columns    — list of column names in the constraint
        duplicates — list of {value, ids} dicts describing the offending rows
    """

    def __init__(
        self,
        table: str,
        constraint: str,
        columns: list[str],
        duplicates: list[dict[str, object]],
    ) -> None:
        self.table = table
        self.constraint = constraint
        self.columns = columns
        self.duplicates = duplicates
        super().__init__(self._format())

    def _format(self) -> str:
        col_label = ", ".join(self.columns)
        lines = [f"Неможливо додати унікальне обмеження на «{col_label}»: знайдено дублікати:"]
        for dup in self.duplicates:
            lines.append(f"  • значення {dup['value']!r} — записи: {dup['ids']}")
        lines.append("Виправте дублікати та повторіть операцію.")
        return "\n".join(lines)


def invalidate_table_cache(doctype_name: str) -> None:
    """Remove a cached Table for the given DocType (call on update/delete)."""
    _TABLE_CACHE.pop(doctype_name, None)


# ── MultiLink junction table ─────────────────────────────────────────────

MULTI_LINK_TABLE = Table(
    "grunt_core_multi_link",
    SA_METADATA,
    Column("parent_doctype", String(255), nullable=False, primary_key=True),
    Column("parent_name", String(255), nullable=False, primary_key=True),
    Column("parent_field", String(255), nullable=False, primary_key=True),
    Column("idx", Integer, default=0, primary_key=True),
    Column("link_doctype", String(255), nullable=False),
    Column("link_name", String(255), nullable=False),
    Index(
        "ix_grunt_core_multi_link_parent_parentfield_idx",
        "parent_doctype",
        "parent_name",
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
        Column("name", String(255), primary_key=True),
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
                Column("parent_name", String(255), nullable=False),
                Column("parent_doctype", String(255), nullable=False),
                Column("parent_field", String(255), nullable=False),
                Column("idx", Integer, default=0),
            ]
        )

    # Names already claimed by system columns — skip any user field that would conflict.
    _system_cols = frozenset(
        {
            "name",
            "owner",
            "created_at",
            "modified_at",
            "modified_by",
            "docstatus",
            "parent_name",
            "parent_doctype",
            "parent_field",
            "idx",
        }
    )

    # User-defined fields
    for field in doctype.fields:
        if field.fieldtype in NON_PHYSICAL_FIELDS:
            continue
        if field.fieldname in _system_cols:
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
        if field.fieldname in _system_cols:
            continue
        if field.unique:
            uq_name = f"uq_{table_name}_{field.fieldname}"
            constraints.append(UniqueConstraint(field.fieldname, name=uq_name))

    # Non-unique indexes
    for field in doctype.fields:
        if field.fieldname in _system_cols:
            continue
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

    def _sync(connection):
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
                    col_length = getattr(col.type, "length", None)
                    if col_length is not None and max_stored > col_length:
                        logger.warning(
                            "compiler.skip_varchar_reduction",
                            table=table.name,
                            column=col.name,
                            current_max=max_stored,
                            new_length=col_length,
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
        # SQLite exposes unique indexes via get_indexes (not get_unique_constraints),
        # so merge both sources for a complete picture.
        existing_uq: set[str] = {ix["name"] for ix in insp.get_unique_constraints(table.name)}
        existing_uq |= {ix["name"] for ix in insp.get_indexes(table.name) if ix.get("unique")}
        desired_uq: dict[str, UniqueConstraint] = {
            str(c.name): c for c in table.constraints if isinstance(c, UniqueConstraint) and c.name
        }
        uq_prefix = f"uq_{table.name}_"
        is_sqlite = connection.dialect.name == "sqlite"

        for name, uq in desired_uq.items():
            if name not in existing_uq:
                uq_cols = [c.name for c in uq.columns]
                cols_sql = ", ".join(f'"{c}"' for c in uq_cols)
                # Partial index: uniqueness applies only to non-NULL, non-empty values.
                # Empty strings are treated the same as NULL (not provided).
                where_nonempty = " AND ".join(
                    f'("{c}" IS NOT NULL AND "{c}" != \'\')' for c in uq_cols
                )

                # Safety: raise with details if non-empty data has duplicates
                dup_rows = connection.execute(
                    text(
                        f"SELECT {cols_sql}, GROUP_CONCAT(name) as ids, COUNT(*) as cnt "
                        f'FROM "{table.name}" '
                        f"WHERE {where_nonempty} "
                        f"GROUP BY {cols_sql} HAVING COUNT(*) > 1"
                    )
                ).fetchall()
                if dup_rows:
                    duplicates = [
                        {
                            "value": row[0] if len(uq_cols) == 1 else tuple(row[: len(uq_cols)]),
                            "ids": row[-2],  # GROUP_CONCAT(name)
                        }
                        for row in dup_rows
                    ]
                    raise DuplicateDataError(table.name, name, uq_cols, duplicates)

                # Use a partial unique index for both dialects so that NULL and
                # empty-string values are exempt from the uniqueness check.
                connection.execute(
                    text(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" '
                        f'ON "{table.name}" ({cols_sql}) '
                        f"WHERE {where_nonempty}"
                    )
                )
                logger.info("compiler.unique_added", table=table.name, constraint=name)

        # Drop stale per-field unique indexes (those with our naming prefix only)
        for name in existing_uq:
            if name and name.startswith(uq_prefix) and name not in desired_uq:
                if is_sqlite:
                    connection.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                else:
                    # Index may have been created via CREATE UNIQUE INDEX or ADD CONSTRAINT
                    try:
                        connection.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                    except Exception:
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
