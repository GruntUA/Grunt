"""The storage of a DocType - where its rows live, behind one interface.

The layers above (documents, lists, reports) speak :class:`~grunt.query.query.Query`
and plain row dicts; a store executes them. Permissions are not a store's
concern: :mod:`grunt.query.run` ANDs them onto a query's ``where`` before it
gets here, and the document pipeline checks them before a write.

A store says what it can do in :attr:`Store.capabilities`; the core refuses
what's missing with a clear error instead of failing on a table that isn't
there.
"""

from typing import Any, ClassVar

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grunt import _
from grunt.document.serde import serialize_datetimes, with_doctype
from grunt.query.query import Query
lazy from grunt.auth.doctypes.User.user import User

# What a store can do, beyond reading its rows (``fetch``/``count``/``get``).
INSERT = "insert"
UPDATE = "update"
DELETE = "delete"
#: GROUP BY / SUM over the rows (``aggregate``).
AGGREGATE = "aggregate"
#: Rows of other DocTypes that point at a document can be repointed (merge,
#: delete with ``replace_with``) and the document renamed.
REFERENCES = "references"
#: Updates are kept as versions / activity diffs.
HISTORY = "history"
#: Batched SQL work over many rows at once (bulk delete in one statement).
BULK = "bulk"
#: The rows are a SQL table: raw conditions (``list_filter_extra``), reports
#: and their joins, trees, year buckets, ``grunt.db``'s raw writes - and list
#: caches, since the rows change only through the document pipeline.
SQL = "sql"


class Store:
    """The rows of one DocType, read and written in *session*.

    The base stores nothing: no rows, every write refused. Subclasses -
    :class:`~grunt.store.sql.SqlStore` (the DocType's table) and
    :class:`~grunt.store.virtual.VirtualStore` (rows from anywhere) - fill in
    what they can and list it in :attr:`capabilities`.
    """

    capabilities: ClassVar[frozenset[str]] = frozenset()
    #: Why an insert/update/delete this store doesn't do is refused (405) -
    #: mark it with ``N_()``; translated when raised.
    not_supported_message: ClassVar[str | None] = None

    def __init__(self, meta: Any, session: AsyncSession) -> None:
        self.meta = meta
        self.session = session

    @property
    def doctype(self) -> str:
        return self.meta.name

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def unsupported(self) -> HTTPException:
        """405 for an operation this store doesn't do."""
        if self.not_supported_message:
            detail = _(self.not_supported_message)
        else:
            detail = _("“%(doctype)s” does not support this operation") % {"doctype": self.doctype}
        return HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=detail)

    # Reading

    @property
    def columns(self) -> frozenset[str] | None:
        """The values a stored row can hold, or ``None`` - any value."""
        return None

    async def fetch(self, query: Query) -> list[dict[str, Any]]:
        """The rows of *query*, in its order, paged by ``limit``/``offset``/``after``."""
        return []

    async def count(self, query: Query) -> int:
        """How many rows *query* matches, paging ignored."""
        return 0

    async def aggregate(self, query: Query) -> list[dict[str, Any]]:
        """One row per group of ``group_by`` with ``aggregates``, ordered by ``sort``."""
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_("“%(doctype)s” has no table to aggregate") % {"doctype": self.doctype},
        )

    async def distinct(self, field: str) -> list[Any]:
        """The distinct non-empty values of *field* over all rows."""
        return []

    async def get(self, name: str, *, expand: list[str] | None = None) -> dict[str, Any] | None:
        """The stored document *name* (a singleton's only one, whatever *name*),
        or ``None``. *expand* lists the child tables and MultiLink fields to load
        (``None`` - all, ``[]`` - the bare row); a store without them ignores it."""
        return None

    # Writing

    async def insert(
        self, doc: dict[str, Any], *, input: dict[str, Any], user: User
    ) -> dict[str, Any]:
        """Store the new document *doc* and return it as stored (a store may
        name it, add computed values). *input* - the values as submitted."""
        raise self.unsupported()

    async def update(
        self,
        name: str,
        doc: dict[str, Any],
        *,
        before: dict[str, Any],
        input: dict[str, Any],
        user: User,
    ) -> dict[str, Any]:
        """Store *doc* - the document *name* (stored as *before*) with the
        changes *input* applied - and return it as :meth:`output` shows it."""
        raise self.unsupported()

    async def delete(self, name: str, *, before: dict[str, Any]) -> None:
        """Remove the stored document *name* (stored as *before*)."""
        raise self.unsupported()

    async def output(self, doc: dict[str, Any]) -> dict[str, Any]:
        """A stored document as the API returns it."""
        return with_doctype(self.doctype, serialize_datetimes(dict(doc)))


__all__ = [
    "AGGREGATE",
    "BULK",
    "DELETE",
    "HISTORY",
    "INSERT",
    "REFERENCES",
    "SQL",
    "UPDATE",
    "Store",
]
