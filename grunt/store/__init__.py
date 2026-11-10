"""Where a DocType's rows live - see ``DB_LAYERS_PLAN.md``, step 4.

``store_for(meta)`` - the :class:`Store` of a DocType: what its controller
names in ``store_class``, else :class:`SqlStore` (its table) - or, for a
virtual DocType, the empty :class:`Store`. Reads with permissions go through
:mod:`grunt.permissions.reads`, writes through the document pipeline - not a
store directly.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.local import _session_ctx
from grunt.store.base import (
    AGGREGATE,
    BULK,
    DELETE,
    HISTORY,
    INSERT,
    REFERENCES,
    SQL,
    UPDATE,
    Store,
)
from grunt.store.sql import SqlStore
from grunt.store.virtual import Unavailable, VirtualStore
lazy from grunt.document.registry import document_registry


def store_class(meta: Any) -> type[Store]:
    """The store class of *meta*'s DocType."""
    cls = getattr(document_registry.get(meta.name), "store_class", None)
    if cls is not None:
        return cls
    return SqlStore if meta.has_table else Store


def supports(meta: Any, capability: str) -> bool:
    """Whether *meta*'s store can do *capability* - without a session (a class
    attribute), so a check before any work costs nothing."""
    return capability in store_class(meta).capabilities


def store_for(meta: Any, session: AsyncSession | None = None) -> Store:
    """The store of *meta*'s DocType, working in *session* (the current one by default)."""
    session = session or _session_ctx.get()
    if session is None:
        raise RuntimeError("grunt.store: no active session — are you inside a request or hook?")
    return store_class(meta)(meta, session)


__all__ = [
    "AGGREGATE",
    "BULK",
    "DELETE",
    "HISTORY",
    "INSERT",
    "REFERENCES",
    "SQL",
    "UPDATE",
    "SqlStore",
    "Store",
    "Unavailable",
    "VirtualStore",
    "store_class",
    "store_for",
    "supports",
]
