import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from grunt import log
from grunt.config import settings
from grunt.db.dialects import dialect_for
from grunt.document.serde import to_json
lazy from grunt.db.profiler import attach_query_profiler
lazy from grunt.monitoring.perf import attach_sql_counter

# Context variable to hold the name of the currently active site
current_site: ContextVar[str] = ContextVar("current_site", default="")


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
        site_file = self.sites_dir / site_name / "grunt.site"
        if not site_file.exists():
            return {}
        try:
            return json.loads(site_file.read_text())
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
            return dialect_for(db_url).resolve_url(db_url, self.sites_dir / site_name)

        # Fallback to local sqlite db in the site folder
        site_db_path = (self.sites_dir / site_name / "grunt.db").resolve()
        return f"sqlite+aiosqlite:///{site_db_path}"

    def get_engine(self, site_name: str) -> AsyncEngine:
        """Get or create an SQLAlchemy AsyncEngine for the site."""
        if site_name not in self.engines:
            db_url = self.get_database_url(site_name)

            dialect = dialect_for(db_url)
            engine_kwargs: dict[str, Any] = {
                "echo": settings.database_echo,
                "pool_pre_ping": True,
                **dialect.engine_kwargs(),
            }
            # to_json: документи тримають date/Decimal, а типовий json.dumps їх не вміє
            engine = create_async_engine(db_url, json_serializer=to_json, **engine_kwargs)
            dialect.setup_engine(engine)

            attach_sql_counter(engine)

            if settings.sql_profiler_enabled:
                attach_query_profiler(engine, threshold_ms=settings.slow_query_threshold_ms)

            self.engines[site_name] = engine
            self.session_makers[site_name] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            # Safe logging: avoid logging password
            safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
            log.debug("site_manager.engine_created", site=site_name, db_url=safe_url)

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
