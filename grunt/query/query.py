"""A query as data - which rows of a DocType, in what order, how many.

A :class:`Query` is what a store executes (:mod:`grunt.store`) and what
:mod:`grunt.query.run` secures: row-level permissions are ANDed onto
:attr:`Query.where` there, so a read path can't skip them.
"""

from dataclasses import dataclass, replace
from typing import Any

from grunt.query.nodes import TRUE, Expr, and_


@dataclass(frozen=True, slots=True)
class Sort:
    """Order by *field* (a column or, in an aggregate, a label).

    In a row query empty values come last either way and ``name`` breaks ties,
    so the order - and a keyset (:attr:`Query.after`) into it - is total.
    """

    field: str
    descending: bool = True


@dataclass(frozen=True, slots=True)
class Query:
    """The rows of *doctype* matching *where*.

    ``fields`` - ``None`` for whole rows; unknown fields are skipped, a MultiLink
    field comes back as the list of linked names. ``after`` - the
    ``(sort value, name)`` of the last row of the previous page: rows after it
    in the ``sort`` order (``offset`` is then ignored). ``search`` - the list
    search box text. ``group_by`` / ``aggregates`` (``(label, "sum(amount)")``) -
    for :meth:`grunt.store.Store.aggregate` only.
    """

    doctype: str
    where: Expr = TRUE
    fields: tuple[str, ...] | None = None
    sort: Sort | None = None
    limit: int | None = None
    offset: int = 0
    after: tuple[Any, str] | None = None
    search: str | None = None
    group_by: tuple[str, ...] = ()
    aggregates: tuple[tuple[str, str], ...] = ()

    def narrowed(self, expr: Expr) -> Query:
        """This query with *expr* ANDed onto its ``where``."""
        return replace(self, where=and_(self.where, expr))


__all__ = ["Query", "Sort"]
