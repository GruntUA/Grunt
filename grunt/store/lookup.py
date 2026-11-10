"""Which store a DocType's rows live in - :func:`store_for`.

Kept apart from the package's ``__init__`` so the stores themselves
(:mod:`grunt.store.virtual` resolving a Link hop) can look up another
DocType's store without importing the package back.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.local import _session_ctx
from grunt.store.base import Store
from grunt.store.sql import SqlStore

# DocType name -> its controller class; set by grunt.document.registry, so the
# store layer never imports the document layer.
_controller_of: Callable[[str], Any] | None = None


def use_controllers(lookup: Callable[[str], Any]) -> None:
    """Where :func:`store_class` finds a DocType's controller (its ``store_class``)."""
    global _controller_of
    _controller_of = lookup


def store_class(meta: Any) -> type[Store]:
    """The store class of *meta*'s DocType."""
    controller = _controller_of(meta.name) if _controller_of is not None else None
    cls = getattr(controller, "store_class", None)
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
