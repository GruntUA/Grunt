"""Shared test fixtures — single test engine and session override."""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from grunt.core.db.base import Base
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import SA_METADATA, MULTI_LINK_TABLE, compile_doctype_to_table
from grunt.core.metadata.registry import doctype_registry
from grunt.core.search.service import search_index_service
from grunt.main import app

import grunt.core.db.system_tables  # noqa: F401
import grunt.core.auth.models  # noqa: F401

# ── Single shared test engine ─────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite://"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
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

# Override engine for docs router
from grunt.api.v1.docs.utils import get_engine  # noqa: E402


async def override_get_engine():
    return test_engine


app.dependency_overrides[get_engine] = override_get_engine

# Override engine for meta.py (uses get_engine dependency, already overridden above)
from grunt.core.db.session import get_engine as _get_engine_dep  # noqa: E402, F811

app.dependency_overrides[_get_engine_dep] = override_get_engine


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after. Clear registry."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    doctype_registry._doctypes.clear()

    # Remove previously compiled dynamic doctype tables from SA_METADATA
    # Preserve static tables (e.g. grunt_core_multi_link) defined at module level
    _static_tables = {MULTI_LINK_TABLE.name}
    to_remove = [t for t in SA_METADATA.tables if t.startswith("grunt_") and t not in _static_tables]
    for name in to_remove:
        if name in SA_METADATA.tables:
            SA_METADATA.remove(SA_METADATA.tables[name])

    # Compile and create core doctype tables from JSON files, and register in doctype_registry
    import json
    from pathlib import Path
    from grunt.core.metadata.doctype import DocType as _DocType
    _core_dir = Path(__file__).parent.parent / "grunt" / "core" / "doctypes"
    for _dt_file in sorted(_core_dir.glob("**/*.json")):
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
    await search_index_service.ensure_table(test_engine)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(SA_METADATA.drop_all)
        await conn.run_sync(Base.metadata.drop_all)

    # Remove dynamic doctype tables; preserve static tables (e.g. grunt_core_multi_link)
    # so they stay in SA_METADATA and get re-created by the next test's create_all.
    _static_tables = {MULTI_LINK_TABLE.name}
    to_remove = [t for t in SA_METADATA.tables if t.startswith("grunt_") and t not in _static_tables]
    for name in to_remove:
        if name in SA_METADATA.tables:
            SA_METADATA.remove(SA_METADATA.tables[name])


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
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Register a superadmin user and return auth headers."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@grunt.example.com", "password": "secret", "full_name": "Admin"},
    )
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@grunt.example.com", "password": "secret"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
