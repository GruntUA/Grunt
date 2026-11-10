"""Carrying out a schema plan - ``check`` it against the data, then ``apply`` it.

``check`` looks at the rows before anything changes: a unique index can't go
on duplicate values (:class:`DuplicateDataError` - nothing is applied), a
shorter VARCHAR can't hold values longer than it (that change is left out and
logged). ``apply`` runs each change through the dialect, which knows its
backend's DDL. A type change that needs a table rebuild is applied only when
the caller allows it (``grunt migrate``) - otherwise logged and left for then.
"""

from typing import Any

from sqlalchemy import text, update

from grunt.db.dialects import Dialect
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
from grunt.db.schema.diff import is_varchar_reduction
from grunt.i18n import _
from grunt.log import log


class DuplicateDataError(Exception):
    """A unique index can't be added: rows already share a value.

    ``table``, ``constraint``, ``columns`` - what was to be unique; ``duplicates`` -
    ``{value, ids}`` of every offending group.
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
        lines = [
            _("Cannot add a unique constraint on “%(field)s”: duplicates found:")
            % {"field": col_label}
        ]
        for dup in self.duplicates:
            lines.append(
                "  • "
                + _("value %(value)s, records: %(ids)s")
                % {"value": repr(dup["value"]), "ids": dup["ids"]}
            )
        lines.append(_("Fix the duplicates and try again."))
        return "\n".join(lines)


def _duplicates(connection: Any, dialect: Dialect, change: AddUnique) -> list[dict[str, object]]:
    q = dialect.quote
    cols = ", ".join(q(connection, c) for c in change.columns)
    nonempty = " AND ".join(
        f"({q(connection, c)} IS NOT NULL AND {q(connection, c)} != '')" for c in change.columns
    )
    rows = connection.execute(
        text(
            f"SELECT {cols}, {dialect.group_concat_sql(q(connection, 'name'))} AS ids "
            f"FROM {q(connection, change.table.name)} WHERE {nonempty} "
            f"GROUP BY {cols} HAVING COUNT(*) > 1"
        )
    ).fetchall()
    width = len(change.columns)
    return [
        {"value": row[0] if width == 1 else tuple(row[:width]), "ids": row[width]} for row in rows
    ]


def check(connection: Any, dialect: Dialect, changes: list[Change]) -> list[Change]:
    """*changes* that the data allows - raises :class:`DuplicateDataError` for a
    unique index over duplicates; leaves out a VARCHAR shortening that would cut
    stored values (logged)."""
    allowed: list[Change] = []
    for change in changes:
        if isinstance(change, AddUnique):
            duplicates = _duplicates(connection, dialect, change)
            if duplicates:
                raise DuplicateDataError(
                    change.table.name, change.name, list(change.columns), duplicates
                )
        if isinstance(change, AlterType) and is_varchar_reduction(
            change.column.type, change.current
        ):
            longest = dialect.max_text_length(connection, change.table.name, change.column.name)
            length = getattr(change.column.type, "length", None)
            if length is not None and longest > length:
                log.warning(
                    "schema.skip_varchar_reduction",
                    table=change.table.name,
                    column=change.column.name,
                    current_max=longest,
                    new_length=length,
                )
                continue
        allowed.append(change)
    return allowed


def apply(
    connection: Any, dialect: Dialect, changes: list[Change], *, rebuild: bool = False
) -> int:
    """Run *changes* (already checked); returns how many were applied.

    *rebuild* - also apply type changes that rebuild the table (else logged).
    """
    applied = 0
    inline_uniques: dict[str, list[str]] = {}
    rebuilds: dict[str, tuple[Any, list[str]]] = {}
    for change in changes:
        table = change.table.name
        match change:
            case CreateTable():
                change.table.metadata.create_all(connection, tables=[change.table])
            case AddColumn(column=column, backfill=backfill):
                dialect.add_column(connection, table, column)
                if backfill is not None:
                    connection.execute(
                        update(change.table).where(column.is_(None)).values({column.name: backfill})
                    )
            case AlterType(column=column, rebuild=needs_rebuild):
                if needs_rebuild and not rebuild:
                    log.warning(
                        "schema.type_change_deferred",
                        table=table,
                        column=column.name,
                        hint="applied by grunt migrate",
                    )
                    continue
                if needs_rebuild:  # one rebuild per table, after the loop
                    rebuilds.setdefault(table, (change.table, []))[1].append(column.name)
                    continue
                dialect.alter_column_type(connection, table, column)
            case AddUnique(name=name, columns=columns):
                dialect.create_unique(connection, table, name, columns)
            case DropUnique(name=name, is_index=is_index):
                if not dialect.drop_unique_index(connection, table, name, is_index=is_index):
                    inline_uniques.setdefault(table, []).append(name)
                    continue
            case AddIndex(index=index):
                index.create(connection)
            case DropIndex(name=name):
                dialect.drop_index(connection, table, name)
            case DropColumn(name=name, indexes=indexes):
                for index_name in indexes:
                    dialect.drop_index(connection, table, index_name)
                dialect.drop_column(connection, table, name)
        log.info("schema.applied", change=change.describe())
        applied += 1
    for desired, columns in rebuilds.values():
        dialect.rebuild_column_types(connection, desired, columns)
        log.info("schema.applied", change=f"rebuild {desired.name} for {', '.join(columns)}")
        applied += len(columns)
    for table, names in inline_uniques.items():
        applied += dialect.drop_inline_unique(connection, table, sorted(names))
    return applied


__all__ = ["DuplicateDataError", "apply", "check"]
