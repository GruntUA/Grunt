"""One schema change each - what :func:`grunt.db.schema.diff.diff` plans and a
dialect applies. Plain data: a plan can be printed (``grunt migrate --dry-run``),
checked and tested without a database.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Column, Index, Table


@dataclass(frozen=True)
class CreateTable:
    table: Table

    def describe(self) -> str:
        return f"create table {self.table.name}"


@dataclass(frozen=True)
class AddColumn:
    """A new column - added as NULL (the table may have rows), then filled with
    the field's static default (``backfill``), what a new document would get."""

    table: Table
    column: Column
    backfill: Any = None

    def describe(self) -> str:
        return f"add column {self.table.name}.{self.column.name}"


@dataclass(frozen=True)
class AlterType:
    """The column's type changes. ``rebuild`` - the backend can't ALTER a type
    (SQLite): the table is rebuilt with the rows copied over."""

    table: Table
    column: Column
    current: Any
    rebuild: bool = False

    def describe(self) -> str:
        how = " (rebuild the table)" if self.rebuild else ""
        return (
            f"change type of {self.table.name}.{self.column.name}: "
            f"{type(self.current).__name__} -> {self.column.type}{how}"
        )


@dataclass(frozen=True)
class AddUnique:
    """A per-field unique index - partial: empty values (NULL, ``''``) are exempt."""

    table: Table
    name: str
    columns: tuple[str, ...]

    def describe(self) -> str:
        return f"add unique {self.name} ({', '.join(self.columns)})"


@dataclass(frozen=True)
class DropUnique:
    """A unique index or constraint the definition no longer has. ``is_index`` -
    a standalone index (else declared inside CREATE TABLE)."""

    table: Table
    name: str
    is_index: bool

    def describe(self) -> str:
        return f"drop unique {self.name}"


@dataclass(frozen=True)
class AddIndex:
    table: Table
    index: Index

    def describe(self) -> str:
        return f"add index {self.index.name}"


@dataclass(frozen=True)
class DropIndex:
    table: Table
    name: str

    def describe(self) -> str:
        return f"drop index {self.name}"


@dataclass(frozen=True)
class DropColumn:
    """A column no field defines any more - only when the plan was asked to drop
    (``grunt db trim-tables``, removing an app's extension fields)."""

    table: Table
    name: str
    #: Indexes that cover the column - dropped first (SQLite refuses otherwise).
    indexes: tuple[str, ...] = field(default=())

    def describe(self) -> str:
        return f"drop column {self.table.name}.{self.name}"


type Change = (
    CreateTable | AddColumn | AlterType | AddUnique | DropUnique | AddIndex | DropIndex | DropColumn
)

__all__ = [
    "AddColumn",
    "AddIndex",
    "AddUnique",
    "AlterType",
    "Change",
    "CreateTable",
    "DropColumn",
    "DropIndex",
    "DropUnique",
]
