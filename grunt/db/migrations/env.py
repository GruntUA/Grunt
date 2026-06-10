"""Alembic env.py — configured for Grunt system tables.

Reads database_url from grunt.config.settings so the URL lives in .env only.
target_metadata points to the shared MetaData that includes all system tables.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure system table definitions are imported so metadata knows about them
import grunt.db.system_tables as _system_tables  # noqa: F401

# ── Grunt imports ────────────────────────────────────────────────────────
from grunt.config import settings
from grunt.db.base import metadata
from grunt.site.manager import site_manager

# ── Alembic config ──────────────────────────────────────────────────────
config = context.config


def _convert_async_url_to_sync(db_url: str) -> str:
    """
    Convert an async SQLAlchemy database URL to a sync variant for Alembic.

    Only the driver portion (before '://') is inspected and potentially
    rewritten, so other occurrences of these substrings in the URL are left
    untouched.
    """
    mapping = {
        "+aiosqlite": "",
        "+asyncpg": "+psycopg2",
        "+aiomysql": "+pymysql",
    }

    if "://" not in db_url:
        return db_url

    prefix, rest = db_url.split("://", 1)

    for async_suffix, sync_suffix in mapping.items():
        if prefix.endswith(async_suffix):
            prefix = prefix[: -len(async_suffix)] + sync_suffix
            break

    return prefix + "://" + rest


# Use site_manager to get the site-specific database URL (resolves relative SQLite paths)
try:
    site_name = site_manager.get_active_site()
    db_url = site_manager.get_database_url(site_name)
except Exception:
    db_url = settings.database_url
db_url = _convert_async_url_to_sync(db_url)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
