"""What a table needs to become what its DocType says - ``diff``.

The desired table is the compiled one (:func:`grunt.metadata.compiler.compile_doctype_to_table`);
the actual one is read from the database once (:func:`read_actual`). ``diff``
compares the two without touching the database and returns the changes, in
the order they apply. Columns and indexes are dropped only when asked: a column
can hold data nobody defines any more, and several DocTypes can share a table
(``table_name``) - ``keep`` names what the others still need.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, Table, UniqueConstraint, inspect

from grunt.db.schema.changes import (
    AddColumn,
    AddIndex,
    AddUnique,
    AlterType,
    Change,
    CreateTable,
    DropColumn,
    DropIndex,
    DropUnique,
)

# DB-reported type names -> the canonical SQLAlchemy ones, for comparison.
_TYPE_ALIASES: dict[str, str] = {
    "VARCHAR": "STRING",
    "CHAR": "STRING",
    "BIGINT": "INTEGER",
    "SMALLINT": "INTEGER",
    "TINYINT": "INTEGER",
    # Postgres reflects DOUBLE PRECISION as DOUBLE_PRECISION. REAL / MySQL FLOAT are
    # 4-byte and stay distinct so sync widens them to DOUBLE.
    "DOUBLE_PRECISION": "DOUBLE",
    "DOUBLE PRECISION": "DOUBLE",
    "DECIMAL": "NUMERIC",
    "TIMESTAMP": "DATETIME",
}


def _normalize_type(name: str) -> str:
    return _TYPE_ALIASES.get(name.upper(), name.upper())


def type_changed(desired: Any, current: Any, sa_dialect: Any) -> bool:
    """Whether the desired SQLAlchemy type differs from the reflected one.

    PostgreSQL compiles a timestamp as ``TIMESTAMP WITH TIME ZONE`` but reflects
    ``TIMESTAMP(timezone=True)``: the base types are compared, then the zone.
    """
    compiled = desired.compile(sa_dialect).upper()
    with_zone = "WITH TIME ZONE" in compiled and "WITHOUT TIME ZONE" not in compiled
    base = compiled.split("(")[0].replace(" WITHOUT TIME ZONE", "").replace(" WITH TIME ZONE", "")
    desired_str = _normalize_type(base.strip())
    if desired_str != _normalize_type(type(current).__name__):
        return True
    zone = getattr(current, "timezone", None)
    return desired_str == "DATETIME" and zone is not None and bool(zone) != with_zone


def is_varchar_reduction(desired: Any, current: Any) -> bool:
    """Both are strings and the desired length is shorter than the current one."""
    if not isinstance(desired, String):
        return False
    current_len = getattr(current, "length", None)
    desired_len = getattr(desired, "length", None)
    return bool(current_len and desired_len and desired_len < current_len)


@dataclass(frozen=True)
class Actual:
    """A table as the database has it."""

    #: Column name -> reflected type.
    columns: dict[str, Any]
    #: Unique constraints declared inside CREATE TABLE -> their columns.
    uniques: dict[str, tuple[str, ...]]
    #: Unique indexes -> their columns (SQLite reports partial uniques only here).
    unique_indexes: dict[str, tuple[str, ...]]
    #: Other indexes -> their columns.
    indexes: dict[str, tuple[str, ...]]


def read_actual(connection: Any, table_name: str) -> Actual | None:
    """*table_name* as the database has it, or ``None`` - there is no such table."""
    insp = inspect(connection)
    if not insp.has_table(table_name):
        return None
    uniques = {
        str(uq["name"]): tuple(uq["column_names"])
        for uq in insp.get_unique_constraints(table_name)
        if uq.get("name")
    }
    unique_indexes: dict[str, tuple[str, ...]] = {}
    indexes: dict[str, tuple[str, ...]] = {}
    for ix in insp.get_indexes(table_name):
        name = ix.get("name")
        if not name:
            continue
        cols = tuple(c for c in ix["column_names"] if c)
        (unique_indexes if ix.get("unique") else indexes)[name] = cols
    return Actual(
        columns={c["name"]: c["type"] for c in insp.get_columns(table_name)},
        uniques=uniques,
        unique_indexes=unique_indexes,
        indexes=indexes,
    )


def diff(
    table: Table,
    actual: Actual | None,
    *,
    sa_dialect: Any,
    can_alter_type: bool,
    drop_columns: bool = False,
    drop_indexes: bool = False,
    keep: Collection[str] = (),
) -> list[Change]:
    """The changes that make *actual* what *table* says, in the order they apply.

    *can_alter_type* - the backend can ALTER a column's type (else a type change
    is planned as a table rebuild). *drop_columns* / *drop_indexes* - also drop
    columns and our own indexes (``ix_<table>_…``) the definition no longer has,
    except those in *keep* (needed by another DocType on the same table).
    """
    if actual is None:
        return [CreateTable(table)]

    changes: list[Change] = []
    desired_columns = {c.name for c in table.columns}
    for col in table.columns:
        current = actual.columns.get(col.name)
        if current is None:
            changes.append(AddColumn(table, col, col.info.get("backfill_default")))
        elif type_changed(col.type, current, sa_dialect):
            changes.append(AlterType(table, col, current, rebuild=not can_alter_type))

    existing_unique = actual.uniques | actual.unique_indexes
    desired_unique = {
        str(c.name): tuple(col.name for col in c.columns)
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name
    }
    for name, cols in desired_unique.items():
        if name not in existing_unique:
            changes.append(AddUnique(table, name, cols))
    uq_prefix = f"uq_{table.name}_"
    for name in sorted(existing_unique):
        if name.startswith(uq_prefix) and name not in desired_unique and name not in keep:
            changes.append(DropUnique(table, name, is_index=name in actual.unique_indexes))

    desired_indexes = {str(ix.name) for ix in table.indexes if ix.name}
    for ix in sorted(table.indexes, key=lambda i: str(i.name)):
        if ix.name and ix.name not in actual.indexes and ix.name not in existing_unique:
            changes.append(AddIndex(table, ix))
    if drop_indexes:
        ix_prefix = f"ix_{table.name}_"
        for name in sorted(actual.indexes):
            if name.startswith(ix_prefix) and name not in desired_indexes and name not in keep:
                changes.append(DropIndex(table, name))

    if drop_columns:
        unused = [n for n in actual.columns if n not in desired_columns and n not in keep]
        changes.extend(column_drops(table, actual, unused))
    return changes


def column_drops(table: Table, actual: Actual, names: Collection[str]) -> list[DropColumn]:
    """Dropping the columns *names* that *actual* has - each with the indexes
    over it, dropped first (SQLite refuses to drop an indexed column)."""
    covering = {**actual.indexes, **actual.unique_indexes}
    return [
        DropColumn(
            table, name, indexes=tuple(sorted(ix for ix, cols in covering.items() if name in cols))
        )
        for name in names
        if name in actual.columns
    ]


def describe(changes: list[Change]) -> list[str]:
    """The plan as lines for a person (``grunt migrate --dry-run``)."""
    return [change.describe() for change in changes]


__all__ = [
    "Actual",
    "column_drops",
    "describe",
    "diff",
    "is_varchar_reduction",
    "read_actual",
    "type_changed",
]
