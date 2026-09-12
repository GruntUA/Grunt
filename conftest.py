"""Shared test fixtures — single test engine and session override."""

from __future__ import annotations

import logging
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from grunt.config import settings
from grunt.db.base import metadata
from grunt.db.session import get_engine as _get_engine_dep
from grunt.db.session import get_session
from grunt.main import app
from grunt.metadata.compiler import SA_METADATA, compile_doctype_to_table, get_compiled_metadata
from grunt.metadata.registry import doctype_registry
from grunt.search.service import search_index_service
from grunt.site.manager import current_site

# Disable rate limiting for tests
settings.rate_limit_enabled = False

# Fixed DocType-registry key for the whole test process. Set explicitly via
# the same ContextVar production code uses (see grunt.metadata.registry),
# rather than relying on SiteManager.get_active_site()'s file-based fallback
# — several tests monkeypatch site_manager.bench_dir/sites_dir mid-test to
# simulate a different site, which would otherwise change which registry
# instance resolves and silently "lose" whatever setup_db just loaded.
_TEST_SITE = "__pytest__"

# ── Single shared test engine ─────────────────────────────────────────────
# Override via env to test against PostgreSQL or MySQL:
#   TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/grunt_test pytest
#   TEST_DATABASE_URL=mysql+aiomysql://user:pass@localhost/grunt_test pytest

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


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


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after. Clear registry."""
    site_token = current_site.set(_TEST_SITE)
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
            await conn.run_sync(metadata.create_all)
        doctype_registry.reset()

        from grunt.workflow.registry import clear_cache as _clear_workflow_cache

        _clear_workflow_cache()

        # Remove previously compiled dynamic doctype tables from this test
        # process's compiled-table MetaData (kept separate from SA_METADATA,
        # which only ever holds fixed-shape infra tables like MULTI_LINK_TABLE).
        compiled_metadata = get_compiled_metadata()
        to_remove = [t for t in compiled_metadata.tables if t.startswith("grunt_")]
        for name in to_remove:
            compiled_metadata.remove(compiled_metadata.tables[name])

        # Compile and create core doctype tables from JSON files, and register in doctype_registry
        import json

        from grunt.metadata.doctype import DocType as _DocType
        from grunt.startup.doctypes import _find_doctype_dirs

        _dt_files = sorted(f for d in _find_doctype_dirs() for f in d.glob("**/*.json"))
        for _dt_file in _dt_files:
            try:
                _dt_data = json.loads(_dt_file.read_text(encoding="utf-8"))
                _dt_obj = _DocType.model_validate(_dt_data)
                compile_doctype_to_table(_dt_obj)
                doctype_registry._doctypes[_dt_obj.name] = _dt_obj
            except Exception as exc:
                # Log and continue so a single bad doctype file does not break all tests.
                logging.getLogger(__name__).warning(
                    "Failed to load or compile doctype from %s: %s", _dt_file, exc
                )
        async with test_engine.begin() as conn:
            await conn.run_sync(SA_METADATA.create_all)
            await conn.run_sync(compiled_metadata.create_all)
        await search_index_service.ensure_table(test_engine)

        # Seed a permissive SystemSettings row so the production password /
        # registration policy (grunt/auth/password_policy.py, register gate) does
        # not block unrelated tests. Tests that exercise the policy set strict
        # values themselves and call grunt.site.settings.clear_settings_cache().
        from datetime import UTC, datetime

        from grunt.site.settings import clear_settings_cache

        clear_settings_cache()
        try:
            _ss = compile_doctype_to_table(doctype_registry._doctypes["SystemSettings"])
            _now = datetime.now(UTC)
            async with test_engine.begin() as conn:
                await conn.execute(
                    _ss.insert().values(
                        name="SystemSettings",
                        owner="system@grunt.local",
                        created_at=_now,
                        modified_at=_now,
                        modified_by="system@grunt.local",
                        docstatus=0,
                        allow_user_registration=True,
                        password_min_length=1,
                        password_require_uppercase=False,
                        password_require_lowercase=False,
                        password_require_numbers=False,
                        password_require_symbols=False,
                        enable_web_push=False,
                    )
                )
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).warning("SystemSettings test seed failed: %s", exc)
        clear_settings_cache()

        yield

        async with test_engine.begin() as conn:
            await conn.run_sync(compiled_metadata.drop_all)
            await conn.run_sync(SA_METADATA.drop_all)
            await conn.run_sync(metadata.drop_all)

        # Remove dynamic doctype tables from the compiled-table MetaData; next
        # test's setup_db rebuilds them from scratch.
        to_remove = [t for t in compiled_metadata.tables if t.startswith("grunt_")]
        for name in to_remove:
            compiled_metadata.remove(compiled_metadata.tables[name])
    finally:
        current_site.reset(site_token)


@pytest.fixture
async def db_session(setup_db):
    """Provide a database session backed by test_engine.

    Use this fixture instead of importing TestSessionLocal directly,
    to avoid the double-import issue (conftest loaded by pytest vs tests.conftest).
    """
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
def engine(setup_db):
    """Provide the test engine instance."""
    return test_engine


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def ctx(db_session: AsyncSession, engine: AsyncEngine):
    """Provide an active grunt context with SYSTEM_USER for tests."""
    from grunt.app import grunt as grunt_app
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with grunt_app.context(db_session, engine, SYSTEM_USER):
        yield grunt_app


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Register a superadmin user and return auth headers."""
    r_reg = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.register_full_name_api",
        json={"email": "admin@grunt.example.com", "password": "secret", "full_name": "Admin User"},
    )
    assert r_reg.status_code in (201, 200, 409)  # 409 if user somehow persisted

    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.User.user.login_api",
        json={"email": "admin@grunt.example.com", "password": "secret"},
    )
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
