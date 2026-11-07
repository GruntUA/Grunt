"""Running a :class:`~grunt.query.query.Query` - the one read path with
row-level permissions in it.

Every function takes either ``user=`` (the rows that user may read: role
``match`` rules, shares, User Permissions - :func:`read_predicate`) or
``ignore_permissions=True``, and refuses neither or both: skipping
permissions is spelled out at the call, never an omission. ``session`` - the
current one by default.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import _
from grunt.errors import not_found
from grunt.permissions.query import read_predicate
from grunt.query.query import Query
from grunt.store import Store, store_for
lazy from grunt.auth.doctypes.User.user import User


async def _meta(doctype: str) -> Any:
    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return dt


async def _secured(
    query: Query, user: User | None, ignore_permissions: bool, session: AsyncSession | None
) -> tuple[Store, Query]:
    """The DocType's store and *query* narrowed to what *user* may read."""
    if (user is None) == (not ignore_permissions):
        raise TypeError("pass either user= or ignore_permissions=True")
    dt = await _meta(query.doctype)
    if user is not None:
        query = query.narrowed(await read_predicate(user, dt))
    return store_for(dt, session), query


async def fetch(
    query: Query,
    *,
    user: User | None = None,
    ignore_permissions: bool = False,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """The rows of *query*."""
    store, query = await _secured(query, user, ignore_permissions, session)
    return await store.fetch(query)


async def count(
    query: Query,
    *,
    user: User | None = None,
    ignore_permissions: bool = False,
    session: AsyncSession | None = None,
) -> int:
    """How many rows *query* matches (``limit``/``offset``/``after`` ignored)."""
    store, query = await _secured(query, user, ignore_permissions, session)
    return await store.count(query)


async def page(
    query: Query,
    *,
    user: User | None = None,
    ignore_permissions: bool = False,
    with_total: bool = True,
    session: AsyncSession | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """The rows of *query* and - ``with_total`` - how many match in all, under
    the same predicate (the pagination total never counts rows the page hides)."""
    store, query = await _secured(query, user, ignore_permissions, session)
    total = await store.count(query) if with_total else None
    return await store.fetch(query), total


async def aggregate(
    query: Query,
    *,
    user: User | None = None,
    ignore_permissions: bool = False,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """The groups of *query* (``group_by``) with its ``aggregates``."""
    store, query = await _secured(query, user, ignore_permissions, session)
    return await store.aggregate(query)


__all__ = ["aggregate", "count", "fetch", "page"]
