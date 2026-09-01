"""Helpers for running Alembic migrations programmatically, per site.

``grunt db migrate`` calls :func:`upgrade_site` for every site so the Alembic
version history is applied alongside the metadata/table sync. Standalone
``alembic upgrade head`` still works — ``env.py`` falls back to the active site
when no explicit URL is handed in through ``config.attributes["target_db_url"]``.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# apps/grunt/alembic.ini
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

_ASYNC_TO_SYNC = {
    "+aiosqlite": "",
    "+asyncpg": "+psycopg2",
    "+aiomysql": "+pymysql",
}


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
    if db_url:
        cfg.attributes["target_db_url"] = async_url_to_sync(db_url)
    return cfg


def upgrade_site(db_url: str, revision: str = "head", *, sql: bool = False) -> None:
    """Run ``alembic upgrade <revision>`` against ``db_url`` (a site's DB URL).

    ``sql=True`` emits the SQL instead of executing it (offline / dry-run mode).
    """
    command.upgrade(make_config(db_url), revision, sql=sql)


def sync_site(db_url: str) -> str:
    """Bring a site's Alembic history in line, assuming system tables already exist.

    The framework's migrations are incremental patches on top of
    ``metadata.create_all`` — they are not runnable from an empty database. So:

    * **no revision scripts** (``versions/`` is empty — the default in dev, until
      the first migration is written for a release): there is no history to
      apply. Skip.
    * **no ``alembic_version`` table** (fresh site, or one that predates Alembic):
      the tables ``create_all`` just built are already at head — ``stamp head``
      records that without running any migration.
    * **``alembic_version`` present**: ``upgrade head`` applies whatever is pending.

    Returns ``"no migrations"``, ``"stamped"`` or ``"upgraded"``.
    """
    cfg = make_config(db_url)

    if not list(ScriptDirectory.from_config(cfg).walk_revisions()):
        return "no migrations"

    sync_url = async_url_to_sync(db_url)
    engine = sa.create_engine(sync_url, poolclass=sa.pool.NullPool)
    try:
        has_version = sa.inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()

    if has_version:
        command.upgrade(cfg, "head")
        return "upgraded"
    command.stamp(cfg, "head")
    return "stamped"
