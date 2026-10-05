import unicodedata
from contextlib import suppress
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from grunt import log
from grunt.config import settings

_UK_ALPHABET = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
_UK_ORDER = {ch: i for i, ch in enumerate(_UK_ALPHABET)}


def _uk_sort_key(s: str) -> str:
    """Return a sort key string that respects Ukrainian alphabetical order.

    Maps each Ukrainian letter to a code point in the Private Use Area
    (U+E000+) so that comparison of resulting strings gives correct
    Ukrainian alphabetical order, regardless of Unicode code points.
    """
    if not s:
        return ""
    out = []
    for ch in unicodedata.normalize("NFC", s).casefold():
        pos = _UK_ORDER.get(ch)
        if pos is not None:
            out.append(chr(0xE000 + pos))  # Private Use Area, keeps uk order
        else:
            out.append(ch)
    return "".join(out)


# Context variable to hold the name of the currently active site
current_site: ContextVar[str] = ContextVar("current_site", default="")


def text_sort_expr(col: Any, dialect_name: str) -> Any:
    """Return a dialect-aware sort expression for text columns.

    * SQLite - uses the custom ``uk_sort_key()`` SQLite function registered
                at connect time, which maps Ukrainian letters to Private Use
                Area code points for correct alphabetical ordering.
    * PostgreSQL - ``col COLLATE "C"`` with lower() for a portable fallback.
                   For full Ukrainian ordering install the ``uk_UA`` ICU
                   collation and use ``col.collate('uk-x-icu')``.
    * MySQL - ``CONVERT(col USING utf8mb4) COLLATE utf8mb4_unicode_ci``
                gives good case-insensitive, accent-sensitive ordering.
    """
    from sqlalchemy import func  # noqa: PLC0415

    if dialect_name == "sqlite":
        return func.uk_sort_key(col)
    if dialect_name == "mysql":
        return func.lower(col)
    # postgresql and everything else
    return func.lower(col)


_UNSET = object()


class SiteManager:
    """Manages multi-tenant sites and their database connections.

    Assumes sites are stored in `my-bench/sites/`.
    Each site has its own `.env` and optionally `grunt.db` (for SQLite).
    """

    def __init__(self) -> None:
        # Шукаємо bench_dir: спочатку вгору від cwd, потім від розташування пакету
        bench_dir = self._find_bench_dir(Path.cwd()) or self._find_bench_dir(
            Path(__file__).resolve()
        )
        if bench_dir is None:
            # No ancestor of cwd or of this file has both apps/ and sites/ -
            # guess two levels up from cwd (matches apps/<app>/ as cwd, the
            # common case when running a bench command from an app dir).
            bench_dir = Path.cwd().parent.parent.resolve()
            log.warning(
                "site_manager.bench_dir_guessed",
                cwd=str(Path.cwd()),
                guessed=str(bench_dir),
            )

        self.bench_dir = bench_dir.resolve()
        self.sites_dir = self.bench_dir / "sites"

        # Caches
        self.engines: dict[str, AsyncEngine] = {}
        self.session_makers: dict[str, async_sessionmaker[AsyncSession]] = {}
        self._primary_web_app: Any = _UNSET

    @staticmethod
    def _find_bench_dir(start: Path) -> Path | None:
        """Walk up from *start* looking for a directory that has both apps/ and sites/."""
        check = start if start.is_dir() else start.parent
        for _ in range(8):
            if (check / "apps").is_dir() and (check / "sites").is_dir():
                return check.resolve()
            if check == check.parent:
                break
            check = check.parent
        return None

    def get_sites(self) -> list[str]:
        """List all valid site directories in the bench."""
        if not self.sites_dir.exists():
            return []
        sites = []
        for d in self.sites_dir.iterdir():
            if d.is_dir() and not d.name.startswith(".") and (d / "grunt.site").exists():
                sites.append(d.name)
        return sites

    def get_site_config(self, site_name: str) -> dict[str, Any]:
        """Return a site's ``grunt.site`` config (empty if missing/unreadable)."""
        import json

        site_file = self.sites_dir / site_name / "grunt.site"
        if not site_file.exists():
            return {}
        try:
            return json.loads(site_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.error("site_manager.config_read_error", site=site_name, error=str(exc))
            return {}

    def get_installed_apps(self, site_name: str) -> list[str]:
        """Return the ``installed_apps`` list from a site's ``grunt.site`` config."""
        return list(self.get_site_config(site_name).get("installed_apps", []))

    def get_primary_web_app(self) -> str | None:
        """App whose www/ pages mount at the site root (``primary_web_app`` in
        ``grunt.site``), or ``None`` - then every app's pages live under
        ``/{app_name}/...``.

        Routes are mounted once per process, so this is bench-wide: the first
        site (by name) that sets it wins, and a disagreeing site is logged.
        Cached - changing it needs a restart anyway.
        """
        if self._primary_web_app is not _UNSET:
            return self._primary_web_app
        primary: str | None = None
        for site in sorted(self.get_sites()):
            config = self.get_site_config(site)
            app = config.get("primary_web_app")
            if not app:
                continue
            if app not in config.get("installed_apps", []):
                log.warning("site_manager.primary_web_app.not_installed", site=site, app=app)
            elif primary is None:
                primary = app
            elif primary != app:
                log.warning(
                    "site_manager.primary_web_app.conflict", site=site, app=app, holder=primary
                )
        self._primary_web_app = primary
        return primary

    def get_all_installed_apps(self) -> set[str]:
        """Return the union of apps installed across every site in the bench.

        Used at startup to decide which external apps' code should load: an app
        that is not installed on any site must not have its hooks, controllers,
        or startup tasks run.
        """
        installed: set[str] = set()
        for site in self.get_sites():
            installed.update(self.get_installed_apps(site))
        return installed

    def get_site_env(self, site_name: str) -> dict:
        """Read .env for a given site."""
        env_path = self.sites_dir / site_name / ".env"
        if not env_path.exists():
            return {}
        try:
            return dotenv.dotenv_values(env_path)
        except Exception as e:
            log.error("site_manager.env_read_error", site=site_name, error=str(e))
            return {}

    def get_database_url(self, site_name: str) -> str:
        """Get the database URL for the site."""
        env_vars = self.get_site_env(site_name)
        db_url = env_vars.get("DATABASE_URL", "")

        if db_url:
            # Resolve relative SQLite paths relative to the site directory
            if "sqlite" in db_url and "///." in db_url:
                # e.g. "sqlite+aiosqlite:///./grunt.db" -> dialect + "./grunt.db"
                dialect, _, rel_path = db_url.partition("///")
                abs_path = (self.sites_dir / site_name / rel_path).resolve()
                return f"{dialect}///{abs_path}"
            return db_url

        # Fallback to local sqlite db in the site folder
        site_db_path = (self.sites_dir / site_name / "grunt.db").resolve()
        return f"sqlite+aiosqlite:///{site_db_path}"

    def get_engine(self, site_name: str) -> AsyncEngine:
        """Get or create an SQLAlchemy AsyncEngine for the site."""
        if site_name not in self.engines:
            db_url = self.get_database_url(site_name)

            engine_kwargs: dict[str, Any] = {"echo": settings.database_echo, "pool_pre_ping": True}
            if "postgresql" in db_url:
                engine_kwargs.update({"pool_size": 20, "max_overflow": 10})
            elif "mysql" in db_url:
                engine_kwargs.update(
                    {
                        "pool_size": 20,
                        "max_overflow": 10,
                        "connect_args": {"charset": "utf8mb4"},
                    }
                )
            elif "sqlite" in db_url:
                # A real (small) pool instead of NullPool: NullPool opens a brand
                # new aiosqlite connection - a new background thread plus the
                # connect-time PRAGMAs below - on every single checkout, which
                # showed up as tens of ms hiding inside the profiler's "BEGIN"
                # span on every request. WAL mode lets several connections read
                # concurrently, and connect_args timeout is SQLite's busy_timeout
                # for the rare writer/writer contention, so pooling is safe here.
                engine_kwargs.update(
                    {"pool_size": 5, "max_overflow": 5, "connect_args": {"timeout": 30}}
                )

            engine = create_async_engine(db_url, **engine_kwargs)

            if "sqlite" in db_url:

                @event.listens_for(engine.sync_engine, "connect")
                def _on_sqlite_connect(dbapi_conn, _connection_record):
                    # Hand transaction control fully to SQLAlchemy: pysqlite/aiosqlite's
                    # own implicit BEGIN/COMMIT heuristics otherwise race with
                    # SAVEPOINT (session.begin_nested()) boundaries, causing stray
                    # implicit commits (and, under WAL, real fsync stalls) exactly
                    # at nested-transaction points.
                    dbapi_conn.isolation_level = None
                    with suppress(Exception):
                        cursor = dbapi_conn.cursor()
                        cursor.execute("PRAGMA journal_mode=WAL")
                        cursor.execute("PRAGMA synchronous=NORMAL")
                        # Automatically return freed pages to the OS over time
                        # (INCREMENTAL = pages freed lazily, no full-file rewrite)
                        cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
                        cursor.close()
                        dbapi_conn.create_function("uk_sort_key", 1, _uk_sort_key)
                        # Override SQLite's built-in lower() with a Unicode-aware version
                        # so that ILIKE (which compiles to lower(x) LIKE lower(y)) works
                        # correctly for Cyrillic/Ukrainian characters.
                        dbapi_conn.create_function(
                            "lower", 1, lambda s: s.lower() if isinstance(s, str) else s
                        )

                @event.listens_for(engine.sync_engine, "begin")
                def _on_sqlite_begin(conn):
                    from grunt.db.write_intent import begin_statement  # noqa: PLC0415

                    # IMMEDIATE for work that will write - see grunt/db/write_intent.py.
                    conn.exec_driver_sql(begin_statement())

            if settings.debug:
                from grunt.db.profiler import attach_query_profiler  # noqa: PLC0415

                attach_query_profiler(engine, threshold_ms=settings.slow_query_threshold_ms)

            self.engines[site_name] = engine
            self.session_makers[site_name] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            # Safe logging: avoid logging password
            safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
            log.info("site_manager.engine_created", site=site_name, db_url=safe_url)

        return self.engines[site_name]

    def get_session_maker(self, site_name: str) -> async_sessionmaker[AsyncSession]:
        """Get the session maker for the site."""
        self.get_engine(site_name)  # Ensure it exists
        return self.session_makers[site_name]

    def get_active_site(self) -> str:
        """Get the current active site from the ContextVar."""
        site = current_site.get()
        if not site:
            # Fallback for CLI or single-site test setups
            current_site_file = self.sites_dir / "currentsite.txt"
            if current_site_file.exists():
                site = current_site_file.read_text().strip()
                if site:
                    return site
            raise ValueError("No active site set in context and no currentsite.txt found.")
        return site


site_manager = SiteManager()
