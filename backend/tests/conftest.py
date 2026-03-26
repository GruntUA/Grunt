"""Shared test fixtures — single test engine and session override."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from grunt.core.db.base import Base
from grunt.core.db.session import get_session
from grunt.core.metadata.compiler import SA_METADATA
from grunt.core.metadata.registry import doctype_registry
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
from grunt.api.v1.docs import get_engine  # noqa: E402


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

    # Remove previously compiled dynamic tables from SA_METADATA
    to_remove = [t for t in SA_METADATA.tables if t.startswith("grunt_")]
    for name in to_remove:
        if name in SA_METADATA.tables:
            SA_METADATA.remove(SA_METADATA.tables[name])

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(SA_METADATA.drop_all)
        await conn.run_sync(Base.metadata.drop_all)

    to_remove = [t for t in SA_METADATA.tables if t.startswith("grunt_")]
    for name in to_remove:
        if name in SA_METADATA.tables:
            SA_METADATA.remove(SA_METADATA.tables[name])


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
