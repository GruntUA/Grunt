"""Running a :class:`~grunt.query.query.Query` against its DocType's store -
without permissions.

Every function takes ``ignore_permissions=True``: skipping permissions is
spelled out at the call, never an omission. Reading as a user - the rows and
fields that user may see - is :mod:`grunt.permissions.reads`. ``session`` - the
current one by default.
"""

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.errors import not_found
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.query.query import Query
from grunt.store import Store, store_for


async def _store(query: Query, ignore_permissions: bool, session: AsyncSession | None) -> Store:
    if ignore_permissions is not True:
        raise TypeError(
            "pass ignore_permissions=True - or read as a user (grunt.permissions.reads)"
        )
    dt = await doctype_registry.get_meta(query.doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": query.doctype})
    return store_for(dt, session)


async def fetch(
    query: Query, *, ignore_permissions: Literal[True], session: AsyncSession | None = None
) -> list[dict[str, Any]]:
    """The rows of *query*."""
    return await (await _store(query, ignore_permissions, session)).fetch(query)


async def count(
    query: Query, *, ignore_permissions: Literal[True], session: AsyncSession | None = None
) -> int:
    """How many rows *query* matches (``limit``/``offset``/``after`` ignored)."""
    return await (await _store(query, ignore_permissions, session)).count(query)


async def page(
    query: Query,
    *,
    ignore_permissions: Literal[True],
    with_total: bool = True,
    session: AsyncSession | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """The rows of *query* and - ``with_total`` - how many match in all."""
    store = await _store(query, ignore_permissions, session)
    total = await store.count(query) if with_total else None
    return await store.fetch(query), total


async def aggregate(
    query: Query, *, ignore_permissions: Literal[True], session: AsyncSession | None = None
) -> list[dict[str, Any]]:
    """The groups of *query* (``group_by``) with its ``aggregates``."""
    return await (await _store(query, ignore_permissions, session)).aggregate(query)


__all__ = ["aggregate", "count", "fetch", "page"]
