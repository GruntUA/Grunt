"""Database layer - engine, session, metadata, and high-level helpers."""

from typing import TYPE_CHECKING

from grunt.db.base import metadata
from grunt.db.session import get_engine, get_session

if TYPE_CHECKING:
    from grunt.db.api import GruntDB

__all__ = [
    "metadata",
    "GruntDB",
    "get_engine",
    "get_session",
]

# GruntDB/the module-level proxy are resolved lazily via __getattr__, not
# imported at module scope: grunt.db.api imports grunt.metadata.registry,
# which imports grunt.db.system_tables - a submodule of this package, so
# reaching it always runs this __init__.py first. An eager import here
# closes that loop back on grunt.metadata.registry before it has finished
# defining `doctype_registry`, breaking any first-time import that starts
# from grunt.metadata.registry (e.g. the `grunt` CLI).
_db_proxy = None


def __getattr__(name: str):
    global _db_proxy

    if name == "GruntDB":
        from grunt.db.api import GruntDB

        return GruntDB

    if _db_proxy is None:
        from grunt.db.api import GruntDB

        _db_proxy = GruntDB()

    if hasattr(_db_proxy, name):
        return getattr(_db_proxy, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
