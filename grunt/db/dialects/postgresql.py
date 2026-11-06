"""PostgreSQL."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import String, Table, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql.dml import Insert

from grunt.db.dialects.base import ConstraintViolation, Dialect
from grunt.db.dialects.fulltext import FullText, FullTextSpec, PostgresTsvector
from grunt.i18n import _
lazy from grunt.backups import MAX_COMPRESSION_LEVEL, BackupError

_PG_KINDS = {"23502": "not_null", "23505": "unique", "23503": "foreign_key", "23514": "check"}
_PG_NOT_NULL_COLUMN = re.compile(r'null value in column "([^"]+)"')
_PG_KEY_COLUMNS = re.compile(r"Key \(([^)]+)\)=")
_PG_CONSTRAINT = re.compile(r'constraint "([^"]+)"')
_PG_RELATION = re.compile(r'relation "([^"]+)"')


#: Connection parameters libpq (pg_dump, pg_restore) understands - kept as they are.
_LIBPQ_PARAMS = frozenset(
    {
        "host",
        "hostaddr",
        "port",
        "sslmode",
        "sslrootcert",
        "sslcert",
        "sslkey",
        "sslcrl",
        "sslnegotiation",
        "channel_binding",
        "gssencmode",
        "application_name",
        "options",
        "connect_timeout",
        "target_session_attrs",
        "keepalives",
        "keepalives_idle",
    }
)
#: asyncpg's ``ssl=`` values -> libpq ``sslmode``.
_ASYNCPG_SSL = {"true": "require", "false": "disable", "on": "require", "off": "disable"}


def _libpq_query(query: Any) -> dict[str, Any]:
    """The site URL's query, as libpq takes it: ``ssl`` (asyncpg) becomes
    ``sslmode``, driver-only options (``prepared_statement_cache_size``, ...)
    are dropped - libpq refuses a URI with a parameter it doesn't know."""
    out = {k: v for k, v in query.items() if k in _LIBPQ_PARAMS}
    if "ssl" in query and "sslmode" not in out:
        ssl = str(query["ssl"]).lower()
        out["sslmode"] = _ASYNCPG_SSL.get(ssl, ssl)
    return out


class PostgresDialect(Dialect):
    name = "postgresql"

    async def create_database(self, url: Any, name: str, *, replace: bool = False) -> None:
        # CREATE DATABASE can't run in a transaction and has no IF NOT EXISTS
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                quoted = conn.dialect.identifier_preparer.quote(name)
                if replace:
                    await conn.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
                exists = await conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
                )
                if not exists:
                    await conn.execute(text(f"CREATE DATABASE {quoted}"))
        finally:
            await engine.dispose()

    compaction_scope = "table"

    def engine_kwargs(self) -> dict[str, Any]:
        return {"pool_size": 20, "max_overflow": 10}

    def connect_args(self, url: Any) -> dict[str, Any]:
        # Every datetime in Grunt is UTC. to_char()/date() of a timestamp follow
        # the session's TimeZone (a server in Europe/Kyiv puts 2025-12-31 23:00
        # UTC into 2026) - so the session is UTC, set at connect time: right for
        # timestamptz and naive timestamp columns alike, no per-query conversion.
        driver = make_url(str(url)).get_driver_name()
        if driver == "asyncpg":
            return {"server_settings": {"timezone": "UTC"}}
        if driver.startswith("psycopg"):
            return {"options": "-c timezone=UTC"}
        return {}

    async def empty_tables(self, conn: Any, names: list[str]) -> None:
        # One statement for all; a lock held by a stray connection fails fast
        # instead of hanging the run.
        if not names:
            return
        quote = conn.dialect.identifier_preparer.quote
        await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        await conn.execute(
            text(f"TRUNCATE {', '.join(quote(n) for n in names)} RESTART IDENTITY CASCADE")
        )

    def exact(self, col: Any) -> Any:
        return col.collate("C") if isinstance(col.type, String) else col

    def text_sort(self, col: Any) -> Any:
        # Code point order whatever the database's collation (en_US, uk_UA... order
        # linguistically, and each differently) - "C" exists on every server.
        # lower() itself still follows the database, so Cyrillic lowercases.
        return func.lower(col).collate("C")

    def upsert(self, table: Table, row: dict[str, Any], key: list[str]) -> Insert:
        stmt = pg_insert(table).values(**row)
        return stmt.on_conflict_do_update(
            index_elements=key, set_={k: v for k, v in row.items() if k not in key}
        )

    def fulltext(self, spec: FullTextSpec) -> FullText:
        return PostgresTsvector(spec)

    def date_bucket(self, column: Any, bucket: str) -> Any:
        fmt = {"day": "YYYY-MM-DD", "month": "YYYY-MM", "quarter": 'YYYY-"Q"Q', "year": "YYYY"}
        return func.to_char(column, fmt[bucket])

    async def database_size(self, session: Any) -> int | None:
        return (await session.execute(text("select pg_database_size(current_database())"))).scalar()

    def compaction_command(self, quoted_table: str) -> str:
        # ACCESS EXCLUSIVE on the table while it is rewritten
        return f"VACUUM (FULL, ANALYZE) {quoted_table}"

    def compaction_footprint(self, conn: Any, table_name: str) -> int | None:
        return int(
            conn.execute(text("SELECT pg_total_relation_size(:t)"), {"t": table_name}).scalar() or 0
        )

    def table_storage(self, conn: Any, table_name: str) -> dict[str, Any]:
        row = conn.execute(
            text("SELECT pg_table_size(:t), pg_indexes_size(:t), pg_total_relation_size(:t)"),
            {"t": table_name},
        ).one()
        dead = conn.execute(
            text("SELECT n_dead_tup FROM pg_stat_user_tables WHERE relname = :t"),
            {"t": table_name},
        ).scalar()
        return {
            "table_bytes": int(row[0]),
            "index_bytes": int(row[1]),
            "total_bytes": int(row[2]),
            "size_supported": True,
            "dead_tuples": int(dead or 0),
            "reclaim_scope": "table",
        }

    # ── Errors ──────────────────────────────────────────────────────────────

    def integrity_violation(self, exc: Exception) -> ConstraintViolation | None:
        # Where the driver puts the details: SQLAlchemy's asyncpg adapter keeps
        # the SQLSTATE on the DBAPI error and the asyncpg exception (column_name,
        # constraint_name, ...) as its cause; psycopg 2/3 have ``pgcode`` /
        # ``sqlstate`` and the fields on ``diag``. The message is the last resort.
        orig = getattr(exc, "orig", None) or exc
        native = orig.__cause__ or orig
        diag = getattr(orig, "diag", None)

        def field(name: str, diag_name: str | None = None) -> Any:
            for source in (native, orig):
                if (value := getattr(source, name, None)) is not None:
                    return value
            return getattr(diag, diag_name or name, None) if diag is not None else None

        code = field("sqlstate") or field("pgcode")
        kind = _PG_KINDS.get(str(code))
        if kind is None:
            return None
        message = f"{orig}\n{field('detail', 'message_detail') or ''}"

        column = field("column_name")
        if column is None and kind == "not_null":
            column = m.group(1) if (m := _PG_NOT_NULL_COLUMN.search(message)) else None
        columns: tuple[str, ...] = (column,) if column else ()
        if not columns and (m := _PG_KEY_COLUMNS.search(message)):
            columns = tuple(c.strip().strip('"') for c in m.group(1).split(","))

        constraint = field("constraint_name")
        if constraint is None and (m := _PG_CONSTRAINT.search(message)):
            constraint = m.group(1)
        table = field("table_name")
        if table is None and (m := _PG_RELATION.search(message)):
            table = m.group(1)
        return ConstraintViolation(kind, table, columns, constraint)  # type: ignore[arg-type]

    # ── Backups ─────────────────────────────────────────────────────────────

    dump_suffix = ".pgdump"

    @staticmethod
    def _run_client(tool: str, args: list[str], url: Any) -> None:
        """Run a PostgreSQL client tool against *url*; a failure is a ``BackupError``.

        The password goes in ``PGPASSWORD``, never in the arguments - those are
        visible to every local user in the process list and end up in errors.
        """
        if not shutil.which(tool):
            raise BackupError(
                _("%(tool)s not found; install the PostgreSQL client") % {"tool": tool}
            )
        # URL.set(password=None) keeps the password - build the URL without it
        conninfo = URL.create(
            "postgresql",
            username=url.username,
            host=url.host,
            port=url.port,
            database=url.database,
            query=_libpq_query(url.query),
        )
        env = dict(os.environ)
        if url.password:
            env["PGPASSWORD"] = str(url.password)
        result = subprocess.run(
            [tool, *args, conninfo.render_as_string(hide_password=False)],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or "").strip().splitlines()[-1:] or [str(result.returncode)]
            raise BackupError(_("%(tool)s failed: %(error)s") % {"tool": tool, "error": error[0]})

    def dump(self, url: Any, dest: Path, level: int, progress: Any) -> None:
        """``pg_dump -Fc`` with zstd (pg_dump 16+); its size is unknown up front."""
        level = min(max(level, 1), MAX_COMPRESSION_LEVEL)
        progress.set(stage=_("Dumping the database"))  # pg_dump reports no progress
        self._run_client("pg_dump", ["-Fc", f"--compress=zstd:{level}", "-f", str(dest)], url)

    def restore_dump(self, url: Any, src: Path, aside: Path) -> None:
        # The database URL goes last as a positional dbname, so -d takes it.
        self._run_client(
            "pg_restore", ["--clean", "--if-exists", "--no-owner", str(src), "-d"], url
        )
