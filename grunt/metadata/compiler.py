from collections.abc import Collection
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt import log
from grunt.db.dialects import dialect_for
from grunt.db.schema.apply import apply, check
from grunt.db.schema.changes import Change
from grunt.db.schema.diff import describe, diff, read_actual
from grunt.db.types import UtcDateTime
from grunt.metadata.field import NON_PHYSICAL_FIELDS, get_storage_class
from grunt.utils.strings import to_snake_case
lazy from grunt.metadata.doctype import DocType
lazy from grunt.metadata.registry import _resolve_site_key

# SA MetaData for fixed-shape infrastructure tables that never vary by
# DocType or by site (MULTI_LINK_TABLE, OUTBOX_TABLE below). Kept as a
# single shared MetaData/name since nothing here is ever tenant-specific.
SA_METADATA = MetaData()

# Per-site MetaData for *compiled DocType* tables, keyed by site (the same
# key grunt.metadata.registry._resolve_site_key() resolves). One process can
# serve multiple sites; a compiled Table's shape (columns) depends entirely
# on that site's DocType definition, so it must never be shared across sites
# - a stale/foreign Table object would build SQL against columns that don't
# exist in the site actually being queried (extend_existing=True only adds
# columns, it never removes them).
_SA_METADATA: dict[str, MetaData] = {}

# Table cache keyed by site, then by DocType name. Avoids rebuilding Column
# objects on every call to compile_doctype_to_table().
# Invalidated via invalidate_table_cache() when a DocType is updated or deleted.
_TABLE_CACHE: dict[str, dict[str, Table]] = {}


def get_compiled_metadata(site: str | None = None) -> MetaData:
    """Return the MetaData holding compiled per-DocType tables for *site*.

    Defaults to the ambient current site (see
    ``grunt.metadata.registry._resolve_site_key``). Created lazily and cached.
    """

    key = site or _resolve_site_key()
    return _SA_METADATA.setdefault(key, MetaData())


def invalidate_table_cache(doctype_name: str) -> None:
    """Remove a cached Table for the given DocType (call on update/delete)."""

    _TABLE_CACHE.get(_resolve_site_key(), {}).pop(doctype_name, None)


def clear_table_cache(site: str) -> None:
    """Forget every compiled Table of *site* - they are rebuilt from the
    (re-read) DocTypes on next use.

    Needed after a migration: a Table compiled before it still lists the old
    columns, so a dropped column (``File.path``) failed every SELECT and a new
    one (``File.folder``) was never read or written.
    """
    _TABLE_CACHE.pop(site, None)
    _SA_METADATA.pop(site, None)


# MultiLink junction table

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


# Outbox - side effects written with the change they announce, delivered
# after the commit (grunt.outbox).

OUTBOX_TABLE = Table(
    "grunt_core_outbox",
    SA_METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # Dotted path of the async function that delivers the message.
    Column("handler", String(255), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    # Not before this - a retry waits out its backoff.
    Column("due_at", UtcDateTime(), nullable=False),
    # A delivery in progress holds the row until then (a crashed one lets go).
    Column("claimed_until", UtcDateTime(), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", UtcDateTime(), nullable=False),
    Index("ix_grunt_core_outbox_due_at", "due_at"),
    extend_existing=True,
)


# Helpers


def get_table_name(module: str, doctype_name: str) -> str:
    """Return the physical table name: ``grunt_{module}_{snake_case_name}``."""
    return f"grunt_{module}_{to_snake_case(doctype_name)}"


# Compiler


#: Columns of every DocType table, and those a child table adds.
STANDARD_COLUMNS = ("name", "owner", "created_at", "modified_at", "modified_by")
CHILD_COLUMNS = ("parent_name", "parent_doctype", "parent_field", "idx")


def compile_doctype_to_table(doctype: DocType) -> Table:
    """Convert a :class:`DocType` into a :class:`sqlalchemy.Table`.

    The table includes system columns (``id``, ``name``, ``owner``, timestamps)
    plus one column per physical field.

    Results are cached by (site, DocType name); call
    :func:`invalidate_table_cache` after updating or deleting a DocType so
    the new definition is picked up.
    """
    metadata = get_compiled_metadata()

    cache = _TABLE_CACHE.setdefault(_resolve_site_key(), {})
    cached = cache.get(doctype.name)
    # Guard against stale entries: if the site's MetaData no longer holds the
    # Table (e.g. dropped during tests or hot-reload), rebuild and re-cache.
    if cached is not None and cached.name in metadata.tables:
        return cached

    table_name = doctype.table_name or get_table_name(doctype.module, doctype.name)

    columns: list[Column] = [
        Column("name", String(255), primary_key=True),
        Column("owner", String(255), nullable=False),
        Column("created_at", UtcDateTime()),
        Column("modified_at", UtcDateTime()),
        Column("modified_by", String(255)),
    ]

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

    # track_seen -> JSON list of user emails that have opened this document.
    if getattr(doctype, "track_seen", False) and not doctype.is_child:
        columns.append(Column("_seen", JSON, default=list))

    # Names already claimed by system columns - skip any user field that would conflict.
    _system_cols = frozenset(
        {
            "name",
            "owner",
            "created_at",
            "modified_at",
            "modified_by",
            "_seen",
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
        if field.is_virtual:  # computed on read (read_formula) - no stored column
            continue
        if field.fieldname in _system_cols:
            continue

        try:
            col = field.to_sa_column()
        except ValueError:
            # Non-physical or unknown type - skip silently
            continue

        col.nullable = True
        # Defaults are handled at the application level (the document pipeline),
        # not at the DB column level, to avoid SA compile issues. The static one
        # is kept for the schema sync: a column added to a table with rows gets it.
        backfill = _backfill_default(field)
        if backfill is not None:
            col.info["backfill_default"] = backfill

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

    # Composite indexes (doctype.indexes)
    for idx_fields in doctype.indexes:
        idx_name = f"ix_{table_name}_" + "_".join(idx_fields)
        constraints.append(Index(idx_name, *idx_fields))

    table = Table(table_name, metadata, *columns, *constraints, extend_existing=True)
    cache[doctype.name] = table
    return table


# Sync (create / alter)


def _backfill_default(field: Any) -> Any:
    """The field's static default as a column value, or None when it has none.

    Date/time defaults are skipped: they are tokens like ``"Today"`` meaning
    "at creation", not a value to stamp on rows that already exist.
    """
    if field.default is None or get_storage_class(field.fieldtype) in ("date", "datetime", "time"):
        return None
    try:
        return field.coerce(field.default)
    except TypeError, ValueError:
        return None


def plan_sync(
    connection: Any, table: Table, *, drop_indexes: bool = False, keep: Collection[str] = ()
) -> list[Change]:
    """What :func:`sync_table` would change in *table* (a sync connection)."""
    dialect = dialect_for(connection)
    return diff(
        table,
        read_actual(connection, table.name),
        sa_dialect=connection.dialect,
        can_alter_type=dialect.can_alter_column_type,
        drop_indexes=drop_indexes,
        keep=keep,
        same_type=lambda desired, current: dialect.same_column_type(
            desired, current, connection.dialect
        ),
    )


def table_index_names(table: Table) -> set[str]:
    """The names of *table*'s indexes and unique constraints - what another
    DocType sharing the table needs kept (``keep``)."""
    names = {str(ix.name) for ix in table.indexes if ix.name}
    names |= {str(c.name) for c in table.constraints if isinstance(c, UniqueConstraint) and c.name}
    return names


async def preview_sync(
    doctype: DocType,
    async_engine: AsyncEngine | None = None,
    *,
    session: AsyncSession | None = None,
    drop_indexes: bool = False,
    keep: Collection[str] = (),
) -> list[str]:
    """:func:`sync_table`'s plan for *doctype*, as lines - nothing is changed.

    Reads through *session*'s connection when given - a second connection would
    wait for the session's own lock (SQLite)."""
    if not doctype.has_table:
        return []
    table = compile_doctype_to_table(doctype)

    def plan(c: Any) -> list[Change]:
        return plan_sync(c, table, drop_indexes=drop_indexes, keep=keep)

    if session is not None:
        conn = await session.connection()
        return describe(await conn.run_sync(plan))
    if async_engine is None:
        raise ValueError("preview_sync needs an engine or a session")
    async with async_engine.connect() as conn:
        return describe(await conn.run_sync(plan))


async def sync_table(
    doctype: DocType,
    async_engine: AsyncEngine | None,
    session: AsyncSession | None = None,
    *,
    rebuild: bool = False,
    drop_indexes: bool = False,
    keep: Collection[str] = (),
) -> bool:
    """Bring the DocType's table in line with its definition (:mod:`grunt.db.schema`):
    create it, add columns, change types, sync unique indexes, add indexes.
    Columns are **never** dropped here. *rebuild* - also change column types
    that need a table rebuild (SQLite); *drop_indexes* - also drop our indexes
    the definition no longer has, except *keep* (another DocType on the same
    table needs them) - ``grunt migrate`` passes both.

    Returns True if anything in the database was changed.

    When *session* is provided, uses its underlying connection instead of
    opening a new one (avoids SQLite "database is locked" errors).
    """
    if not doctype.has_table:
        log.debug("compiler.skip_virtual", doctype=doctype.name)
        return False

    table = compile_doctype_to_table(doctype)

    def _sync(connection) -> bool:
        dialect = dialect_for(connection)
        planned = plan_sync(connection, table, drop_indexes=drop_indexes, keep=keep)
        changes = check(connection, dialect, planned)
        return apply(connection, dialect, changes, rebuild=rebuild) > 0

    if session is not None:
        conn = await session.connection()
        return await conn.run_sync(_sync)
    if async_engine is None:
        raise ValueError("sync_table needs an engine or a session")
    async with async_engine.begin() as conn:
        return await conn.run_sync(_sync)
