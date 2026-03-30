from contextvars import ContextVar
from pathlib import Path
from typing import Dict

import dotenv
import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from grunt.config import settings

logger = structlog.get_logger()

# Context variable to hold the name of the currently active site
current_site: ContextVar[str] = ContextVar("current_site", default="")

class SiteManager:
    """Manages multi-tenant sites and their database connections.
    
    Assumes sites are stored in `my-bench/sites/`.
    Each site has its own `.env` and optionally `grunt.db` (for SQLite).
    """

    def __init__(self) -> None:
        # Знаходимо bench_dir: шукаємо вгору директорію з apps/ та sites/
        cwd = Path.cwd()
        bench_dir = None
        check = cwd
        for _ in range(5):
            if (check / "apps").is_dir() and (check / "sites").is_dir():
                bench_dir = check
                break
            if check == check.parent:
                break
            check = check.parent

        if bench_dir is None:
            # Fallback: cwd.parent.parent (legacy)
            bench_dir = cwd.parent.parent.resolve()

        self.bench_dir = bench_dir.resolve()
        self.sites_dir = self.bench_dir / "sites"

        # Caches
        self.engines: Dict[str, AsyncEngine] = {}
        self.session_makers: Dict[str, async_sessionmaker[AsyncSession]] = {}

    def get_sites(self) -> list[str]:
        """List all valid site directories in the bench."""
        if not self.sites_dir.exists():
            return []
        sites = []
        for d in self.sites_dir.iterdir():
            if d.is_dir() and not d.name.startswith(".") and (d / "grunt.site").exists():
                sites.append(d.name)
        return sites

    def get_site_env(self, site_name: str) -> dict:
        """Read .env for a given site."""
        env_path = self.sites_dir / site_name / ".env"
        if not env_path.exists():
            return {}
        try:
            return dotenv.dotenv_values(env_path)
        except Exception as e:
            logger.error("site_manager.env_read_error", site=site_name, error=str(e))
            return {}

    def get_database_url(self, site_name: str) -> str:
        """Get the database URL for the site."""
        env_vars = self.get_site_env(site_name)
        db_url = env_vars.get("DATABASE_URL", "")

        if db_url:
            # Resolve relative SQLite paths relative to the site directory
            if "sqlite" in db_url and "///." in db_url:
                # e.g. "sqlite+aiosqlite:///./grunt.db" → dialect + "./grunt.db"
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
            
            engine_kwargs = {"echo": settings.debug, "pool_pre_ping": True}
            if "postgresql" in db_url:
                engine_kwargs.update({"pool_size": 20, "max_overflow": 10})
                
            engine = create_async_engine(db_url, **engine_kwargs)
            self.engines[site_name] = engine
            self.session_makers[site_name] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            # Safe logging: avoid logging password
            safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
            logger.info("site_manager.engine_created", site=site_name, db_url=safe_url)
            
        return self.engines[site_name]

    def get_session_maker(self, site_name: str) -> async_sessionmaker[AsyncSession]:
        """Get the session maker for the site."""
        self.get_engine(site_name) # Ensure it exists
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
