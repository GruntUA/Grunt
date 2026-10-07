"""Reusable pytest fixtures for testing apps built on grunt.

Grunt's own ``tests/conftest.py`` builds a single-test-engine environment
inline, scoped to ``grunt/*/doctypes/``. External apps (tsnap, hrm, car_ua,
...) need the exact same machinery, plus their own ``{module}/doctypes/``
directories loaded into the registry alongside grunt's core ones, and their
package directory on ``sys.path`` so intra-app imports (e.g.
``car_ua.services.x``) resolve. This module factors that out so each app's
conftest.py doesn't reimplement the SA_METADATA bootstrap/teardown dance.

Usage, in the app's ``tests/conftest.py``::

    from pathlib import Path
    from grunt.testkit import make_app_fixtures

    # Fixtures must live in module globals for pytest to discover them -
    # the factory returns them as a dict for exactly that purpose.
    globals().update(make_app_fixtures(Path(__file__).parent.parent, "tsnap"))
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import grunt
from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.config import settings
from grunt.db.session import get_engine as _get_engine_dep
from grunt.db.session import get_session
from grunt.document.registry import document_registry
from grunt.main import app
from grunt.metadata.compiler import SA_METADATA, compile_doctype_to_table, get_compiled_metadata
from grunt.metadata.doctype import DocType
from grunt.metadata.registry import doctype_registry
from grunt.search.service import search_index_service
from grunt.site.manager import current_site
from grunt.startup.doctypes import _find_doctype_dirs

if TYPE_CHECKING:
    from pathlib import Path

settings.rate_limit_enabled = False

logger = logging.getLogger(__name__)

# Fixed DocType-registry key for the whole test process - set explicitly via
# the same ContextVar production code uses, rather than relying on
# SiteManager.get_active_site()'s file-based fallback (see conftest.py's
# identical _TEST_SITE for the full rationale).
_TEST_SITE = "__pytest__"


def _app_doctype_dirs(app_dir: Path, app_name: str) -> list[Path]:
    app_json = app_dir / "app.json"
    try:
        modules = json.loads(app_json.read_text(encoding="utf-8")).get("modules", [app_name])
    except FileNotFoundError:
        modules = [app_name]
    return [d for m in modules if (d := app_dir / m / "doctypes").is_dir()]


def make_app_fixtures(app_dir: Path, app_name: str) -> dict[str, Any]:
    """Build the standard (setup_db, db_session, engine, ctx, client) fixture set
    for an external app's test suite.

    Set ``TEST_DATABASE_URL`` to point ``test_engine`` at Postgres/MySQL instead
    of the in-memory sqlite default - same convention as grunt's own conftest.
    """
    # Must happen at conftest-import time, not inside a fixture: pytest imports
    # every test module during collection, before any fixture runs, so a test
    # file's module-level `from car_ua.services... import ...` needs this on
    # sys.path already.
    app_dir_str = str(app_dir)
    if app_dir_str not in sys.path:
        sys.path.insert(0, app_dir_str)

    test_db_url = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")
    test_engine = create_async_engine(test_db_url, echo=False)
    TestSessionLocal = async_sessionmaker(  # noqa: N806 - sessionmaker factory, PascalCase by convention
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session

    async def override_get_engine():
        return test_engine

    app.dependency_overrides[_get_engine_dep] = override_get_engine

    @pytest_asyncio.fixture
    async def setup_db():
        """Create tables before each test, drop after. Clear registry.

        Loads grunt's core doctypes plus this app's own. Not autouse (unlike
        grunt core's own conftest): app test directories mix DB-backed tests
        with plain sync unit tests, and pytest-asyncio hard-errors when a sync
        test is forced to depend on an async autouse fixture. Pulled in
        transitively by db_session/engine/ctx/client below - request one of
        those (or setup_db itself) in tests that need the database.
        """
        site_token = current_site.set(_TEST_SITE)
        try:
            doctype_registry.reset()

            compiled_metadata = get_compiled_metadata()
            to_remove = [t for t in compiled_metadata.tables if t.startswith("grunt_")]
            for name in to_remove:
                compiled_metadata.remove(compiled_metadata.tables[name])

            dt_dirs = [*_find_doctype_dirs(), *_app_doctype_dirs(app_dir, app_name)]
            dt_files = sorted(f for d in dt_dirs for f in d.glob("**/*.json"))
            for dt_file in dt_files:
                try:
                    dt_data = json.loads(dt_file.read_text(encoding="utf-8"))
                    dt_obj = DocType.model_validate(dt_data)
                    if not dt_obj.app:
                        dt_obj.app = app_name if dt_file.is_relative_to(app_dir) else "grunt"
                    compile_doctype_to_table(dt_obj)
                    doctype_registry._doctypes[dt_obj.name] = dt_obj
                except Exception as exc:
                    logger.warning("Failed to load or compile doctype from %s: %s", dt_file, exc)

            document_registry.index_external_app_controllers(app_dir)

            async with test_engine.begin() as conn:
                await conn.run_sync(SA_METADATA.create_all)
                await conn.run_sync(compiled_metadata.create_all)
            await search_index_service.ensure_table(test_engine)

            yield

            async with test_engine.begin() as conn:
                await conn.run_sync(compiled_metadata.drop_all)
                await conn.run_sync(SA_METADATA.drop_all)

            to_remove = [t for t in compiled_metadata.tables if t.startswith("grunt_")]
            for name in to_remove:
                compiled_metadata.remove(compiled_metadata.tables[name])
        finally:
            current_site.reset(site_token)

    @pytest_asyncio.fixture
    async def db_session(setup_db):
        async with TestSessionLocal() as session:
            yield session

    @pytest.fixture
    def engine(setup_db) -> AsyncEngine:
        return test_engine

    @pytest_asyncio.fixture
    async def client():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest_asyncio.fixture
    async def ctx(db_session: AsyncSession, engine: AsyncEngine):
        """Provide an active grunt context with SYSTEM_USER for tests."""
        async with grunt.context(db_session, engine, SYSTEM_USER):
            yield grunt

    return {
        "setup_db": setup_db,
        "db_session": db_session,
        "engine": engine,
        "client": client,
        "ctx": ctx,
    }
