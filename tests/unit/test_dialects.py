"""grunt.db.dialects - resolution and the SQL each backend gets."""

from pathlib import Path

import pytest
from sqlalchemy import Column, Date, MetaData, String, Table, select
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.ext.asyncio import create_async_engine

from grunt.db.dialects import (
    Dialect,
    MysqlDialect,
    PostgresDialect,
    SqliteDialect,
    UnknownDatabaseError,
    dialect_for,
    dialect_name,
)

_t = Table("t", MetaData(), Column("title", String), Column("day", Date))


def _sql(expr, sa_dialect) -> str:
    return str(expr.compile(dialect=sa_dialect, compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize(
    ("obj", "expected"),
    [
        ("sqlite", SqliteDialect),
        ("sqlite+aiosqlite:///./grunt.db", SqliteDialect),
        ("postgresql+asyncpg://u:p@h/db", PostgresDialect),
        ("mariadb", MysqlDialect),
        (postgresql.dialect(), PostgresDialect),
    ],
)
def test_dialect_for_resolves_names_urls_and_sa_dialects(obj, expected):
    assert isinstance(dialect_for(obj), expected)


@pytest.mark.parametrize("obj", ["oracle", "", None, object()])
def test_dialect_for_never_guesses(obj):
    with pytest.raises(UnknownDatabaseError):
        dialect_for(obj)


def test_session_without_bind_is_an_error():
    from sqlalchemy.ext.asyncio import AsyncSession

    assert dialect_name(AsyncSession()) is None
    with pytest.raises(UnknownDatabaseError, match="Cannot tell"):
        dialect_for(AsyncSession())


def test_there_is_no_generic_dialect():
    with pytest.raises(TypeError):
        Dialect()  # type: ignore[abstract]


def test_dialect_for_engine():
    engine = create_async_engine("sqlite+aiosqlite://")
    assert isinstance(dialect_for(engine), SqliteDialect)


def test_sqlite_resolves_relative_url_against_site_dir(tmp_path: Path):
    url = SqliteDialect().resolve_url("sqlite+aiosqlite:///./grunt.db", tmp_path)
    assert url == f"sqlite+aiosqlite:///{tmp_path / 'grunt.db'}"
    assert PostgresDialect().resolve_url("postgresql://h/db", tmp_path) == "postgresql://h/db"


def test_text_sort_uses_uk_sort_key_on_sqlite_only():
    assert "uk_sort_key" in _sql(SqliteDialect().text_sort(_t.c.title), sqlite.dialect())
    assert "lower" in _sql(PostgresDialect().text_sort(_t.c.title), postgresql.dialect())


def test_like_contains_keeps_ascii_in_native_like_on_sqlite():
    d = SqliteDialect()
    assert "ILIKE" not in _sql(d.like_contains(_t.c.title, "abc"), postgresql.dialect())
    assert "lower" in _sql(d.like_contains(_t.c.title, "абв"), sqlite.dialect())
    assert "ILIKE" in _sql(PostgresDialect().like_contains(_t.c.title, "abc"), postgresql.dialect())


@pytest.mark.parametrize(
    ("dialect", "sa_dialect", "needle"),
    [
        (SqliteDialect(), sqlite.dialect(), "strftime"),
        (PostgresDialect(), postgresql.dialect(), "to_char"),
        (MysqlDialect(), mysql.dialect(), "date_format"),
    ],
)
def test_date_bucket_per_backend(dialect, sa_dialect, needle):
    for bucket in ("day", "month", "year"):
        assert needle in _sql(dialect.date_bucket(_t.c.day, bucket), sa_dialect)
    assert dialect.date_bucket(_t.c.day, "quarter") is not None


def test_group_concat_is_string_agg_on_postgres():
    # GROUP_CONCAT does not exist in PostgreSQL - the unique-index duplicate
    # check in the compiler used to fail there.
    assert PostgresDialect().group_concat_sql("name").startswith("string_agg(")
    assert SqliteDialect().group_concat_sql("name") == "GROUP_CONCAT(name)"


def test_only_sqlite_cannot_alter_column_type_and_vacuums_whole_db():
    assert not SqliteDialect().can_alter_column_type
    assert PostgresDialect().can_alter_column_type
    assert SqliteDialect().compaction_scope == "database"
    assert SqliteDialect().compaction_command('"t"') == "VACUUM"
    assert PostgresDialect().compaction_scope == "table"
    assert PostgresDialect().compaction_command('"t"') == 'VACUUM (FULL, ANALYZE) "t"'


# ── upsert / full-text ──────────────────────────────────────────────────────

_idx = Table(
    "idx",
    MetaData(),
    Column("ref", String, primary_key=True),
    Column("title", String),
    Column("label", String),
    Column("content", String),
)


def _ft(dialect):
    from grunt.db.dialects.fulltext import FullTextSpec

    spec = FullTextSpec(
        name="s", table=_idx, key="ref", title="title", label="label", content="content"
    )
    return dialect.fulltext(spec)


@pytest.mark.parametrize(
    ("dialect", "sa_dialect", "needle"),
    [
        (SqliteDialect(), sqlite.dialect(), "ON CONFLICT (ref) DO UPDATE"),
        (PostgresDialect(), postgresql.dialect(), "ON CONFLICT (ref) DO UPDATE"),
        (MysqlDialect(), mysql.dialect(), "ON DUPLICATE KEY UPDATE"),
    ],
)
def test_upsert_updates_everything_but_the_key(dialect, sa_dialect, needle):
    stmt = dialect.upsert(_idx, {"ref": "k", "title": "t"}, ["ref"])
    sql = str(stmt.compile(dialect=sa_dialect))
    assert needle in sql
    assert "title" in sql.split(needle.split()[-1], 1)[1]


def test_fulltext_match_per_backend():
    base = select(_idx.c.ref)
    sqlite_sql = str(
        _ft(SqliteDialect()).match(None, base, "петр").compile(dialect=sqlite.dialect())
    )
    assert "JOIN s_fts" in sqlite_sql and "s_fts MATCH" in sqlite_sql and "bm25(s_fts" in sqlite_sql

    pg_sql = str(
        _ft(PostgresDialect()).match(None, base, "петр").compile(dialect=postgresql.dialect())
    )
    assert "to_tsquery" in pg_sql and "ts_rank" in pg_sql

    my_sql = str(_ft(MysqlDialect()).match(None, base, "петр").compile(dialect=mysql.dialect()))
    assert "AGAINST" in my_sql


def test_fulltext_match_falls_back_when_nothing_to_tokenize():
    base = select(_idx.c.ref)
    for dialect in (SqliteDialect(), PostgresDialect(), MysqlDialect()):
        assert _ft(dialect).match(None, base, "-- %%") is None
