"""Where a DocType's rows live - see ``DB_LAYERS_PLAN.md``, step 4.

``store_for(meta)`` - the :class:`Store` of a DocType; :class:`SqlStore` - its
SQL table. Reads with permissions go through :mod:`grunt.query.run`, not a
store directly.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.local import _session_ctx
from grunt.store.base import Store
from grunt.store.sql import SqlStore


def store_for(meta: Any, session: AsyncSession | None = None) -> Store:
    """The store of *meta*'s DocType, reading in *session* (the current one by default)."""
    session = session or _session_ctx.get()
    if session is None:
        raise RuntimeError("grunt.store: no active session — are you inside a request or hook?")
    return SqlStore(meta, session)


__all__ = ["SqlStore", "Store", "store_for"]
