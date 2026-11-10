"""Reading as a user - :mod:`grunt.query.run` narrowed to the rows and fields
that user may see.

Every function takes ``user=`` (an email): the rows that user may read (role
``match`` rules, shares, User Permissions - :func:`read_predicate`), without the
fields hidden from them. Reading without permissions is :mod:`grunt.query.run`
with ``ignore_permissions=True`` - spelled out at the call, never an omission.

A field hidden from the user can't be filtered, sorted, grouped or aggregated
by (403) - each would reveal its values row by row - and the search box doesn't
look in it. Rows come back without it.
"""

from dataclasses import replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.errors import forbidden, not_found
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.permissions.query import read_predicate
from grunt.permissions.roles import role_access
from grunt.query import run
from grunt.query.aggregates import group_field, parse_aggregation
from grunt.query.nodes import And, Expr, Linked, Or
from grunt.query.query import Query


async def _secured(query: Query, user: str) -> tuple[Query, frozenset[str]]:
    """*query* narrowed to what *user* may read, and the fields hidden from them
    (to drop from the rows)."""
    dt = await doctype_registry.get_meta(query.doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": query.doctype})
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
    return query.narrowed(await read_predicate(user, dt)), hidden


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
        target = await doctype_registry.get_meta(expr.doctype)
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
        target = await doctype_registry.get_meta(field.options)
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
    query: Query, *, user: str, session: AsyncSession | None = None
) -> list[dict[str, Any]]:
    """The rows of *query* that *user* may read."""
    query, hidden = await _secured(query, user)
    return _visible(await run.fetch(query, ignore_permissions=True, session=session), hidden)


async def count(query: Query, *, user: str, session: AsyncSession | None = None) -> int:
    """How many rows of *query* *user* may read (``limit``/``offset``/``after`` ignored)."""
    query, _hidden = await _secured(query, user)
    return await run.count(query, ignore_permissions=True, session=session)


async def page(
    query: Query, *, user: str, with_total: bool = True, session: AsyncSession | None = None
) -> tuple[list[dict[str, Any]], int | None]:
    """The rows of *query* *user* may read and - ``with_total`` - how many match in
    all, under the same predicate (the total never counts rows the page hides)."""
    query, hidden = await _secured(query, user)
    rows, total = await run.page(
        query, ignore_permissions=True, with_total=with_total, session=session
    )
    return _visible(rows, hidden), total


async def aggregate(
    query: Query, *, user: str, session: AsyncSession | None = None
) -> list[dict[str, Any]]:
    """The groups of *query* (``group_by``) with its ``aggregates``, over the rows
    *user* may read."""
    query, _hidden = await _secured(query, user)
    return await run.aggregate(query, ignore_permissions=True, session=session)


__all__ = ["aggregate", "count", "fetch", "page"]
