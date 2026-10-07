"""DocType definitions storage - rows of the DocType DocType's own table.

Each DocType is one row: the full definition in the JSON column
``definition`` (source of truth) plus a copy of its scalar properties in
regular columns, so the DocType list filters, sorts and searches like any
other table.

The DocType DocType is the one bootstrap exception: its table has to be known
before a single row can be read, so its shape always comes from the bundled
``DocType.json``, never from the database.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, insert, select, update

from grunt.local import _user_ctx
from grunt.metadata.compiler import compile_doctype_to_table, sync_table
from grunt.metadata.doctype import DocType

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncSession

DEFINITION = "definition"

_DOCTYPE_JSON = Path(__file__).parent / "doctypes" / "DocType" / "DocType.json"


@cache
def bootstrap_doctype() -> DocType:
    """The DocType DocType as bundled with the framework."""
    dt = DocType.model_validate(json.loads(_DOCTYPE_JSON.read_text(encoding="utf-8")))
    dt.app = dt.app or "grunt"
    return dt


def meta_table() -> Table:
    return compile_doctype_to_table(bootstrap_doctype())


async def ensure_table(session: AsyncSession) -> None:
    """Create the DocType table, or add columns for new DocType.json fields."""
    await sync_table(bootstrap_doctype(), None, session=session)


def _to_row(dt: DocType) -> dict[str, Any]:
    data = dt.model_dump()
    row: dict[str, Any] = {
        f.fieldname: f.coerce(data[f.fieldname])
        for f in bootstrap_doctype().fields
        if f.is_physical and f.fieldname in data
    }
    row["name"] = dt.name
    row[DEFINITION] = data
    return row


def _current_user() -> str:
    user = _user_ctx.get()
    return user.email if user is not None else "system"


async def names(session: AsyncSession) -> set[str]:
    table = meta_table()
    return {row[0] for row in await session.execute(select(table.c.name))}


async def exists(session: AsyncSession, name: str) -> bool:
    table = meta_table()
    return await session.scalar(select(table.c.name).where(table.c.name == name)) is not None


async def get_row(session: AsyncSession, name: str) -> dict[str, Any] | None:
    table = meta_table()
    result = await session.execute(select(table).where(table.c.name == name))
    row = result.mappings().one_or_none()
    return dict(row) if row is not None else None


async def get_definition(session: AsyncSession, name: str) -> dict[str, Any] | None:
    table = meta_table()
    return await session.scalar(select(table.c[DEFINITION]).where(table.c.name == name))


async def all_definitions(session: AsyncSession) -> list[dict[str, Any]]:
    table = meta_table()
    result = await session.execute(
        select(table.c[DEFINITION]).where(table.c[DEFINITION].isnot(None))
    )
    return [row[0] for row in result]


async def insert_doctype(session: AsyncSession, dt: DocType) -> None:
    now = datetime.now(UTC)
    user = _current_user()
    await session.execute(
        insert(meta_table()).values(
            **_to_row(dt),
            owner=user,
            created_at=now,
            modified_at=now,
            modified_by=user,
        )
    )


async def update_doctype(session: AsyncSession, dt: DocType) -> None:
    table = meta_table()
    await session.execute(
        update(table)
        .where(table.c.name == dt.name)
        .values(**_to_row(dt), modified_at=datetime.now(UTC), modified_by=_current_user())
    )


async def delete_doctype(session: AsyncSession, name: str) -> None:
    table = meta_table()
    await session.execute(delete(table).where(table.c.name == name))
