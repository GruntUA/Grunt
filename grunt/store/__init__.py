"""Where a DocType's rows live - see ``DB_LAYERS_PLAN.md``, step 4.

``store_for(meta)`` - the :class:`Store` of a DocType: what its controller
names in ``store_class``, else :class:`SqlStore` (its table) - or, for a
virtual DocType, the empty :class:`Store`. Reads with permissions go through
:mod:`grunt.permissions.reads`, writes through the document pipeline - not a
store directly.
"""

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
from grunt.store.lookup import store_class, store_for, supports, use_controllers
from grunt.store.sql import SqlStore
from grunt.store.virtual import Unavailable, VirtualStore

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
    "use_controllers",
]
