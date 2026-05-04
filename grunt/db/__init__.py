"""Database layer — engine, session, base models, and high-level helpers."""

from grunt.db.base import Base, GruntBase
from grunt.db.session import get_engine, get_session

__all__ = [
    "Base",
    "GruntBase",
    "GruntDB",
    "get_engine",
    "get_session",
]

# GruntDB and the module-level proxy are loaded lazily to avoid a circular
# import: grunt.db.api → grunt.metadata.registry → grunt.db.system_tables → grunt.db
_db_proxy = None


def __getattr__(name: str):
    global _db_proxy
    if name == "GruntDB":
        from grunt.db.api import GruntDB  # noqa: PLC0415
        return GruntDB
    if _db_proxy is None:
        from grunt.db.api import GruntDB  # noqa: PLC0415
        _db_proxy = GruntDB()
    if hasattr(_db_proxy, name):
        return getattr(_db_proxy, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
