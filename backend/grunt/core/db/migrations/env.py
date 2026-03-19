"""Alembic env.py — configured for Grunt system tables.

Reads database_url from grunt.config.settings so the URL lives in .env only.
target_metadata points to Base.metadata which includes all system ORM models.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Grunt imports ────────────────────────────────────────────────────────
from grunt.config import settings
from grunt.core.db.base import Base

# Ensure all ORM models are imported so Base.metadata knows about them
import grunt.core.db.system_tables  # noqa: F401
import grunt.core.auth.models  # noqa: F401

# ── Alembic config ──────────────────────────────────────────────────────
config = context.config

# Override sqlalchemy.url from settings (sync driver for Alembic)
db_url = settings.database_url
# Alembic needs a sync driver — swap async drivers for sync equivalents
db_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2").replace("+aiomysql", "+pymysql")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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
