"""Database layer — engine, session, metadata, and high-level helpers."""

from grunt.db.api import GruntDB
from grunt.db.base import metadata
from grunt.db.session import get_engine, get_session

__all__ = [
    "metadata",
    "GruntDB",
    "get_engine",
    "get_session",
]

# Module-level proxy so `import grunt; grunt.db.get_all()` continues to work.
_db_proxy = GruntDB()


def __getattr__(name: str):
    if hasattr(_db_proxy, name):
        return getattr(_db_proxy, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
