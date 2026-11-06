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


def test_text_sort_is_lower_everywhere():
    # No language-specific collation: case ignored, then code points
    assert _sql(SqliteDialect().text_sort(_t.c.title), sqlite.dialect()) == "lower(t.title)"
    # PostgreSQL: whatever the database's collation (en_US orders linguistically)
    pg = _sql(PostgresDialect().text_sort(_t.c.title), postgresql.dialect())
    assert pg == 'lower(t.title) COLLATE "C"'


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


# ── integrity_violation ─────────────────────────────────────────────────────


def _sqlite_error(*statements: str) -> Exception:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (name TEXT PRIMARY KEY, route TEXT NOT NULL, a TEXT, b TEXT)")
    conn.execute('CREATE UNIQUE INDEX "uq_t_route" ON t (route)')
    conn.execute("CREATE UNIQUE INDEX uq_ab ON t (a, b)")
    conn.execute("INSERT INTO t VALUES ('x', 'r', '1', '2')")
    try:
        for statement in statements:
            conn.execute(statement)
    except sqlite3.IntegrityError as exc:
        return exc
    raise AssertionError("no IntegrityError")


def test_sqlite_violations_from_real_errors():
    from sqlalchemy.exc import IntegrityError

    d = SqliteDialect()
    nn = d.integrity_violation(_sqlite_error("INSERT INTO t (name) VALUES ('y')"))
    assert nn == ("not_null", "t", ("route",), None)

    dup = _sqlite_error("INSERT INTO t VALUES ('y', 'r', NULL, NULL)")
    wrapped = IntegrityError("INSERT ...", {}, dup)  # as SQLAlchemy raises it
    assert d.integrity_violation(wrapped) == ("unique", "t", ("route",), None)

    pair = d.integrity_violation(_sqlite_error("INSERT INTO t VALUES ('y', 's', '1', '2')"))
    assert pair is not None and pair.columns == ("a", "b") and pair.column is None

    assert d.integrity_violation(Exception("disk I/O error")) is None


class _AsyncpgError(Exception):
    """What asyncpg raises (the cause of SQLAlchemy's DBAPI error)."""

    def __init__(self, message, **fields):
        super().__init__(message)
        for key, value in fields.items():
            setattr(self, key, value)


def _pg(message, sqlstate, **fields):
    from sqlalchemy.exc import IntegrityError

    native = _AsyncpgError(message, sqlstate=sqlstate, **fields)
    orig = Exception(f"<class 'asyncpg.exceptions.X'>: {message}")
    orig.sqlstate = sqlstate  # type: ignore[attr-defined]
    orig.__cause__ = native
    return IntegrityError("INSERT ...", {}, orig)


def test_postgres_violations_from_asyncpg_fields():
    d = PostgresDialect()
    nn = d.integrity_violation(
        _pg(
            'null value in column "route" of relation "t" violates not-null constraint',
            "23502",
            column_name="route",
            table_name="t",
        )
    )
    assert nn is not None and nn.kind == "not_null" and nn.column == "route"

    dup = d.integrity_violation(
        _pg(
            'duplicate key value violates unique constraint "uq_grunt_core_web_article_route"',
            "23505",
            constraint_name="uq_grunt_core_web_article_route",
            table_name="grunt_core_web_article",
            detail="Key (route)=(/a) already exists.",
        )
    )
    assert dup is not None and dup.kind == "unique" and dup.column == "route"
    assert dup.constraint == "uq_grunt_core_web_article_route"


def test_postgres_violation_falls_back_to_the_message():
    d = PostgresDialect()
    nn = d.integrity_violation(
        _pg('null value in column "route" of relation "t" violates not-null constraint', "23502")
    )
    assert nn is not None and (nn.column, nn.table) == ("route", "t")
    pk = d.integrity_violation(
        _pg(
            'duplicate key value violates unique constraint "t_pkey"\n'
            "DETAIL:  Key (name)=(x) already exists.",
            "23505",
        )
    )
    assert pk is not None and (pk.column, pk.constraint) == ("name", "t_pkey")
    assert d.integrity_violation(_pg("deadlock detected", "40P01")) is None


def test_mysql_violations_from_error_codes():
    from sqlalchemy.exc import IntegrityError

    d = MysqlDialect()
    nn = d.integrity_violation(
        IntegrityError("", {}, Exception(1048, "Column 'route' cannot be null"))
    )
    assert nn is not None and nn.column == "route"
    dup = d.integrity_violation(
        IntegrityError("", {}, Exception(1062, "Duplicate entry '/a' for key 't.uq_t_route'"))
    )
    assert dup == ("unique", "t", (), "uq_t_route")


def test_friendly_error_names_the_field_on_every_backend():
    from grunt.db.errors import _unique_column

    pg = PostgresDialect().integrity_violation(
        _pg(
            'duplicate key value violates unique constraint "uq_grunt_core_web_article_route"',
            "23505",
            table_name="grunt_core_web_article",
        )
    )
    # No column reported - read off the uq_<table>_<field> index name, whole field
    assert _unique_column(pg) == "route"
    from sqlalchemy.exc import IntegrityError

    my = MysqlDialect().integrity_violation(
        IntegrityError("", {}, Exception(1062, "Duplicate entry 'x' for key 't.uq_t_route_name'"))
    )
    assert _unique_column(my) == "route_name"


def test_postgres_violation_from_psycopg_diag():
    from types import SimpleNamespace

    from sqlalchemy.exc import IntegrityError

    orig = Exception('null value in column "route" violates not-null constraint')
    orig.pgcode = "23502"  # type: ignore[attr-defined]  # psycopg2; psycopg 3 says sqlstate
    orig.diag = SimpleNamespace(  # type: ignore[attr-defined]
        column_name="route", constraint_name=None, table_name="t", message_detail=None
    )
    v = PostgresDialect().integrity_violation(IntegrityError("", {}, orig))
    assert v == ("not_null", "t", ("route",), None)


def test_routed_session_tells_its_dialect():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import Session

    engine = create_async_engine("sqlite+aiosqlite://")

    class Routed(Session):  # binds per table - no .bind of its own
        def get_bind(self, mapper=None, clause=None, **kw):
            return engine.sync_engine

    assert isinstance(dialect_for(AsyncSession(sync_session_class=Routed)), SqliteDialect)


@pytest.mark.parametrize(
    ("message", "status"),
    [
        ("FOREIGN KEY constraint failed", 409),
        ("CHECK constraint failed: positive", 422),
        ("NOT NULL constraint failed: t.route", 422),
    ],
)
def test_friendly_error_follows_the_violation_kind(message, status):
    import sqlite3

    from sqlalchemy.exc import IntegrityError

    from grunt.db.errors import friendly_integrity_error

    exc = IntegrityError("", {}, sqlite3.IntegrityError(message))
    http = friendly_integrity_error(exc, None, "sqlite")
    assert http.status_code == status
    assert "unique" not in str(http.detail)


def test_tsvector_constants_are_literals_not_parameters():
    from sqlalchemy.dialects import postgresql

    compiled = _ft(PostgresDialect())._vector("content").compile(dialect=postgresql.dialect())
    # A bound "simple" can't match the GIN index expression under a generic plan
    assert not compiled.params
    assert "'simple'::regconfig" in str(compiled)
