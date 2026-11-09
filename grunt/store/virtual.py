"""``VirtualStore`` - rows that come from anywhere but a table: a ring buffer,
Redis, an API, files on disk.

A subclass says where the rows are (:meth:`VirtualStore.rows`) and, if it can,
how to remove or change one; filters, the search box, sorting, paging and
row-level permissions are applied here, in memory, by the same query AST a SQL
store compiles (:mod:`grunt.query.evaluate`) - so a virtual list filters,
sorts and hides rows exactly like a table one (``tests/contract``).

A ``Linked`` node (a share, a ``match`` through a Link) reads another
DocType: it is resolved first into ``In(values)`` by querying that DocType's
own store.
"""

from typing import Any

from grunt.query import nodes as q
from grunt.query.evaluate import iso, matches
from grunt.query.query import Query, Sort
from grunt.search.terms import matches_text
from grunt.store.base import Store
lazy from grunt.query import run


class Unavailable(Exception):  # noqa: N818 - a state of the source, not a failure of the code
    """The source of a virtual DocType can't be reached (Redis down, not
    configured): its list is empty *because* of that, not because there is
    nothing. The message is shown to the user as it is - mark it for
    translation where it's raised."""


async def resolve_linked(expr: q.Expr) -> q.Expr:
    """*expr* with every ``Linked`` node replaced by ``In`` over the values it
    selects - read through the target DocType's store, without permissions
    (the node itself is the permission rule)."""
    match expr:
        case q.And(items=items):
            return q.and_(*[await resolve_linked(i) for i in items])
        case q.Or(items=items):
            return q.or_(*[await resolve_linked(i) for i in items])
        case q.Linked(field=field, doctype=doctype, where=where, select=column, negate=negate):
            rows = await run.fetch(
                Query(doctype, where=where, fields=(column,)), ignore_permissions=True
            )
            values = tuple(dict.fromkeys(r.get(column) for r in rows if r.get(column) is not None))
            if negate:
                # "not among them" - NULL is neither, as in SQL's NOT IN.
                return q.In(field, values, negate=True) if values else q.Null(field, negate=True)
            return q.In(field, values) if values else q.FALSE
    return expr


def _sort_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()  # as SQL lower() - case ignored, then code points
    return iso(value)


def sort_rows(rows: list[dict[str, Any]], field: str, descending: bool) -> list[dict[str, Any]]:
    """*rows* in the SQL list order: text case ignored, empty values last either
    way, ``name`` breaking ties."""
    present = [r for r in rows if r.get(field) is not None]
    empty = [r for r in rows if r.get(field) is None]

    def key(r: dict[str, Any]) -> tuple[Any, str]:
        return _sort_value(r.get(field)), str(r.get("name", ""))

    try:
        present.sort(key=key, reverse=descending)
    except TypeError:  # mixed types - compare as text
        present.sort(
            key=lambda r: (str(iso(r.get(field))), str(r.get("name", ""))), reverse=descending
        )
    empty.sort(key=lambda r: str(r.get("name", "")), reverse=descending)
    return present + empty


def equals(query: Query, field: str) -> Any:
    """The value *query* requires *field* to equal (``field=value`` among its
    top-level conditions), or ``None`` - for a source that needs it to build
    its rows (a period, a date)."""
    for item in q.conjuncts(query.where):
        if isinstance(item, q.Cmp) and item.field == field and item.op == "eq":
            return item.value
    return None


class VirtualStore(Store):
    """Rows from :meth:`rows`, queried in memory.

    Override :meth:`rows`; override :meth:`get` when one row is cheaper to find
    than all of them; add ``insert``/``update``/``delete`` (and list them in
    ``capabilities``) when the source can change.

    The DocType's settings drive the rest, as for a table: the search box looks
    in ``name``, ``title_field`` and ``search_fields``; ``sort_field`` /
    ``sort_order`` is the order when the requested one names a value the rows
    don't have (a list view asks for ``modified_at`` by default) - ``name``
    without one.
    """

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        """Every row of the source. *query* is a hint (see :func:`equals`): the
        store filters, sorts and pages the result itself. Raise
        :class:`Unavailable` when the source can't be reached."""
        return []

    def _search_fields(self) -> list[str]:
        dt = self.meta
        names: list[str | None] = ["name", dt.title_field, *(dt.search_fields or [])]
        return [f for f in dict.fromkeys(names) if f]

    def _default_sort(self) -> Sort:
        dt = self.meta
        if dt.sort_field:
            return Sort(dt.sort_field, descending=dt.sort_order != "asc")
        return Sort("name", descending=False)

    async def _matching(self, query: Query) -> list[dict[str, Any]]:
        expr = await resolve_linked(query.where)
        rows = [dict(r) for r in await self.rows(query) if matches(expr, r)]
        if query.search:
            fields = [f for f in self._search_fields() if f not in query.search_exclude]
            rows = [r for r in rows if matches_text(query.search, (r.get(f) for f in fields))]
        return rows

    async def fetch(self, query: Query) -> list[dict[str, Any]]:
        rows = await self._matching(query)
        sort = query.sort
        if sort is None or not any(r.get(sort.field) is not None for r in rows):
            sort = self._default_sort()
        rows = sort_rows(rows, sort.field, sort.descending)
        if query.after is not None:
            after_name = query.after[1]
            names = [str(r.get("name")) for r in rows]
            rows = rows[names.index(after_name) + 1 :] if after_name in names else []
        elif query.offset:
            rows = rows[query.offset :]
        if query.limit is not None:
            rows = rows[: query.limit]
        if query.fields:
            wanted = {"name", *query.fields}
            rows = [{k: v for k, v in r.items() if k in wanted} for r in rows]
        return rows

    async def count(self, query: Query) -> int:
        return len(await self._matching(query))

    async def distinct(self, field: str) -> list[Any]:
        values = (r.get(field) for r in await self.rows(Query(self.doctype)))
        return list(dict.fromkeys(v for v in values if v not in (None, "")))

    async def get(self, name: str, *, expand: list[str] | None = None) -> dict[str, Any] | None:
        try:
            rows = await self.rows(Query(self.doctype, where=q.Cmp("name", "eq", name)))
        except Unavailable:
            return None
        return next((dict(r) for r in rows if str(r.get("name")) == name), None)


__all__ = ["Unavailable", "VirtualStore", "equals", "resolve_linked", "sort_rows"]
