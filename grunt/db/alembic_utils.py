"""Helpers for running Alembic migrations programmatically, per site.

``grunt migrate`` calls :func:`upgrade_site` for every site so the Alembic
version history is applied alongside the metadata/table sync. Standalone
``alembic upgrade head`` still works - ``env.py`` falls back to the active site
when no explicit URL is handed in through ``config.attributes["target_db_url"]``.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

import sqlalchemy as sa
lazy from alembic import command
lazy from alembic.config import Config
lazy from alembic.runtime.migration import MigrationContext
lazy from alembic.script import ScriptDirectory
lazy from alembic.util.exc import CommandError

# Importing alembic sets up its plugins with one INFO line each; the imports
# above are lazy, so this runs before alembic is actually loaded.
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)

# apps/grunt/alembic.ini
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

_ASYNC_TO_SYNC = {
    "+aiosqlite": "",
    "+asyncpg": "+psycopg2",
    "+aiomysql": "+pymysql",
}


@contextmanager
def _quiet_alembic() -> Generator[None]:
    """Hide alembic's INFO chatter (plugin setup, "Context impl ...") while
    only inspecting state - a real upgrade/stamp keeps its own output."""
    logger = logging.getLogger("alembic")
    level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        logger.setLevel(level)


def async_url_to_sync(db_url: str) -> str:
    """Rewrite the async driver in a SQLAlchemy URL to its sync equivalent.

    Only the driver portion (before ``://``) is touched.
    """
    if "://" not in db_url:
        return db_url
    prefix, rest = db_url.split("://", 1)
    for async_suffix, sync_suffix in _ASYNC_TO_SYNC.items():
        if prefix.endswith(async_suffix):
            prefix = prefix[: -len(async_suffix)] + sync_suffix
            break
    return f"{prefix}://{rest}"


def make_config(db_url: str | None = None) -> Config:
    """Build an Alembic ``Config`` bound to ``db_url`` (already sync or async)."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    if db_url:
        cfg.attributes["target_db_url"] = async_url_to_sync(db_url)
    return cfg


def upgrade_site(db_url: str, revision: str = "head", *, sql: bool = False) -> None:
    """Run ``alembic upgrade <revision>`` against ``db_url`` (a site's DB URL).

    ``sql=True`` emits the SQL instead of executing it (offline / dry-run mode).
    """
    command.upgrade(make_config(db_url), revision, sql=sql)


class DatabaseAheadError(Exception):
    """The site's database was migrated by newer code than is running now."""

    def __init__(self, revision: str) -> None:
        self.revision = revision
        super().__init__(
            f"the database is at migration {revision!r}, which this code does not have - "
            "it was migrated by a newer release. Switch the code back to that release, "
            "or restore a backup taken before the upgrade (grunt db restore)."
        )


class MigrationState(NamedTuple):
    current: str | None  # the database's revision
    head: str | None  # the code's newest revision
    known: bool  # the code has the database's revision (False = newer release migrated it)


def migration_state(db_url: str) -> MigrationState:
    """Where a site's database stands against this code's Alembic history."""
    script = ScriptDirectory.from_config(make_config(db_url))
    engine = sa.create_engine(async_url_to_sync(db_url), poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    known = True
    if current is not None:
        try:
            script.get_revision(current)
        except CommandError:
            known = False
    return MigrationState(current, script.get_current_head(), known)


def sync_site(db_url: str) -> str:
    """Bring a site's Alembic history in line.

    The framework's migrations are incremental patches for sites created before
    them - they are not runnable from an empty database. So:

    * **no revision scripts** (``versions/`` is empty - the default in dev, until
      the first migration is written for a release): there is no history to
      apply. Skip.
    * **no ``alembic_version`` table** (fresh site, or one that predates Alembic):
      the tables DocType sync builds are already at head - ``stamp head``
      records that without running any migration.
    * **``alembic_version`` present**: ``upgrade head`` applies whatever is pending.

    A revision this code does not know (the code was rolled back past a
    migration) raises :class:`DatabaseAheadError` before anything is touched.

    Returns ``"no migrations"``, ``"stamped"``, ``"up to date"`` or ``"upgraded"``.
    """
    cfg = make_config(db_url)
    with _quiet_alembic():
        script = ScriptDirectory.from_config(cfg)
        if not list(script.walk_revisions()):
            return "no migrations"

        sync_url = async_url_to_sync(db_url)
        engine = sa.create_engine(sync_url, poolclass=sa.pool.NullPool)
        try:
            has_version = sa.inspect(engine).has_table("alembic_version")
        finally:
            engine.dispose()
        state = migration_state(db_url) if has_version else None

    if state is not None:
        if not state.known:
            raise DatabaseAheadError(str(state.current))
        if state.current == state.head:
            return "up to date"
        command.upgrade(cfg, "head")
        return "upgraded"
    command.stamp(cfg, "head")
    return "stamped"
