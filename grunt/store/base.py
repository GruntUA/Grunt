"""The storage protocol - where a DocType's rows live, behind one interface.

The layers above (documents, lists, reports) speak :class:`~grunt.query.query.Query`;
a store executes it. Permissions are not a store's concern: by the time a query
reaches it, :mod:`grunt.query.run` has ANDed them onto ``where``.
"""

from typing import Any, Protocol

from grunt.query.query import Query


class Store(Protocol):
    """The rows of one DocType."""

    async def fetch(self, query: Query) -> list[dict[str, Any]]:
        """The rows of *query*, in its order, paged by ``limit``/``offset``/``after``."""
        ...

    async def count(self, query: Query) -> int:
        """How many rows *query* matches, paging ignored."""
        ...

    async def aggregate(self, query: Query) -> list[dict[str, Any]]:
        """One row per group of ``group_by`` with ``aggregates``, ordered by ``sort``."""
        ...


__all__ = ["Store"]
