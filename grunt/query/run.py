"""Running a :class:`~grunt.query.query.Query` - the one read path with
row-level and field-level permissions in it.

Every function takes either ``user=`` (the rows that user may read: role
``match`` rules, shares, User Permissions - :func:`read_predicate`; without the
fields hidden from them) or ``ignore_permissions=True``, and refuses neither or
both: skipping permissions is spelled out at the call, never an omission.
``session`` - the current one by default.

A field hidden from the user can't be filtered, sorted, grouped or aggregated
by (403) - each would reveal its values row by row - and the search box doesn't
look in it. Rows come back without it.
"""

from dataclasses import replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import _
from grunt.errors import forbidden, not_found
from grunt.permissions.query import read_predicate
from grunt.permissions.roles import role_access
from grunt.query.aggregates import group_field, parse_aggregation
from grunt.query.nodes import And, Expr, Linked, Or
from grunt.query.query import Query
from grunt.store import Store, store_for


async def _meta(doctype: str) -> Any:
    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return dt


async def _secured(
    query: Query, user: str | None, ignore_permissions: bool, session: AsyncSession | None
) -> tuple[Store, Query, frozenset[str]]:
    """The DocType's store, *query* narrowed to what *user* may read, and the
    fields hidden from them (to drop from the rows)."""
    if (user is None) == (not ignore_permissions):
        raise TypeError("pass either user= or ignore_permissions=True")
    dt = await _meta(query.doctype)
    hidden: frozenset[str] = frozenset()
    if user is not None:
        hidden = (await role_access(dt, user)).hidden_fields
        used = await _hidden_used(query, dt, user, hidden)
        if used:
            raise forbidden(
                _("Not permitted to use fields: %(fields)s") % {"fields": ", ".join(sorted(used))}
            )
        if query.search:
            excluded = hidden | await _hidden_behind_links(dt, user)
            if excluded:
                query = replace(query, search_exclude=query.search_exclude | excluded)
        query = query.narrowed(await read_predicate(user, dt))
    return store_for(dt, session), query, hidden


async def _hidden_used(query: Query, dt: Any, user: str, hidden: frozenset[str]) -> set[str]:
    """Fields hidden from *user* that *query* filters, sorts, groups or
    aggregates by - a Link hop's target fields against the target's rules."""
    used = await _hidden_in(query.where, dt, user, hidden)
    if query.sort is not None and query.sort.field in hidden:
        used.add(query.sort.field)
    used.update(f for f in map(group_field, query.group_by) if f in hidden)
    for _label, expr in query.aggregates:
        try:
            field = parse_aggregation(expr)[1]
        except ValueError:
            continue  # the store reports a malformed aggregate itself
        if field in hidden:
            used.add(field)
    return used


async def _hidden_in(expr: Expr, dt: Any, user: str, hidden: frozenset[str]) -> set[str]:
    """Fields of *expr* hidden from *user*; a ``Linked`` node's inner fields
    against its target DocType's rules, reported as ``link_field.target_field``."""
    if isinstance(expr, (And, Or)):
        out: set[str] = set()
        for item in expr.items:
            out |= await _hidden_in(item, dt, user, hidden)
        return out
    field = getattr(expr, "field", None)
    out = {field} if field in hidden else set()
    if isinstance(expr, Linked):
        target = await grunt.get_meta(expr.doctype)
        if target is not None:
            target_hidden = (await role_access(target, user)).hidden_fields
            inner = await _hidden_in(expr.where, target, user, target_hidden)
            out |= {f"{expr.field}.{f}" for f in inner}
    return out


async def _hidden_behind_links(dt: Any, user: str) -> frozenset[str]:
    """``link_field.target_field`` for every column the search box would read
    through a Link (the target's title / search fields) that the target's
    rules hide from *user*."""
    out: set[str] = set()
    for fname in {dt.title_field, *(dt.search_fields or [])} - {None, ""}:
        field = dt.get_field(fname)
        if field is None or not field.has_trait("link") or not field.options:
            continue
        target = await grunt.get_meta(field.options)
        if target is not None:
            out |= {f"{fname}.{f}" for f in (await role_access(target, user)).hidden_fields}
    return frozenset(out)


def _visible(rows: list[dict[str, Any]], hidden: frozenset[str]) -> list[dict[str, Any]]:
    """*rows* without the *hidden* fields (in place)."""
    if hidden:
        for row in rows:
            for field in hidden:
                row.pop(field, None)
    return rows


async def fetch(
    query: Query,
    *,
    user: str | None = None,
    ignore_permissions: bool = False,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """The rows of *query*."""
    store, query, hidden = await _secured(query, user, ignore_permissions, session)
    return _visible(await store.fetch(query), hidden)


async def count(
    query: Query,
    *,
    user: str | None = None,
    ignore_permissions: bool = False,
    session: AsyncSession | None = None,
) -> int:
    """How many rows *query* matches (``limit``/``offset``/``after`` ignored)."""
    store, query, _hidden = await _secured(query, user, ignore_permissions, session)
    return await store.count(query)


async def page(
    query: Query,
    *,
    user: str | None = None,
    ignore_permissions: bool = False,
    with_total: bool = True,
    session: AsyncSession | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """The rows of *query* and - ``with_total`` - how many match in all, under
    the same predicate (the pagination total never counts rows the page hides)."""
    store, query, hidden = await _secured(query, user, ignore_permissions, session)
    total = await store.count(query) if with_total else None
    return _visible(await store.fetch(query), hidden), total


async def aggregate(
    query: Query,
    *,
    user: str | None = None,
    ignore_permissions: bool = False,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """The groups of *query* (``group_by``) with its ``aggregates``."""
    store, query, _hidden = await _secured(query, user, ignore_permissions, session)
    return await store.aggregate(query)


__all__ = ["aggregate", "count", "fetch", "page"]
