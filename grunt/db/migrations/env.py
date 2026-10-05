"""Alembic env.py - configured for Grunt system tables.

Reads database_url from grunt.config.settings so the URL lives in .env only.
target_metadata points to the shared MetaData that includes all system tables.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Grunt imports
from grunt.config import settings

# Ensure system table definitions are imported so metadata knows about them
from grunt.db import system_tables as _system_tables  # noqa: F401
from grunt.db.alembic_utils import async_url_to_sync
from grunt.db.base import metadata
from grunt.site.manager import site_manager

# Alembic config
config = context.config

# A caller (e.g. `grunt db migrate`, which iterates every site) can pin the
# target DB explicitly. Otherwise resolve the active site's URL - that keeps
# a bare `alembic upgrade head` working from the shell.
db_url = config.attributes.get("target_db_url")
if not db_url:
    try:
        db_url = site_manager.get_database_url(site_manager.get_active_site())
    except Exception:
        db_url = settings.database_url
    db_url = async_url_to_sync(db_url)
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
