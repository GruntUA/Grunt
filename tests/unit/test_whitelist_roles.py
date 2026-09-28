"""Unit tests for `@grunt.whitelist(roles=..., require=...)` enforcement.

Enforcement must apply whether the whitelisted function is called through the
HTTP dispatcher (api/v1/method.py) or directly from other Python code — see
grunt.api.context.whitelist for why a passive dispatcher-only check was not
enough (a direct call bypassed it entirely).
"""

from __future__ import annotations

import pytest

import grunt
from grunt.errors import APIError
from tests.support import make_user


@grunt.whitelist(roles=["System Manager"])
async def _admin_only() -> str:
    return "ok"


@grunt.whitelist(require=lambda user: user.email == "special@grunt.example.com")
async def _require_predicate() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_roles_denies_user_without_role(ctx):
    regular = make_user("regular@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx.get_engine(), regular):
        with pytest.raises(APIError) as excinfo:
            await _admin_only()
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_roles_allows_system_manager(ctx):
    admin = make_user("admin@grunt.example.com", is_superadmin=True)
    async with ctx.context(ctx.db._session(), ctx.get_engine(), admin):
        assert await _admin_only() == "ok"


@pytest.mark.asyncio
async def test_roles_allows_matching_role(ctx):
    editor = make_user("editor@grunt.example.com", roles=["System Manager"])
    async with ctx.context(ctx.db._session(), ctx.get_engine(), editor):
        assert await _admin_only() == "ok"


@pytest.mark.asyncio
async def test_roles_denies_guest(ctx):
    async with ctx.context(ctx.db._session(), ctx.get_engine(), None):
        with pytest.raises(APIError) as excinfo:
            await _admin_only()
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_require_predicate_denies_when_false(ctx):
    other = make_user("other@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx.get_engine(), other):
        with pytest.raises(APIError) as excinfo:
            await _require_predicate()
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_require_predicate_allows_when_true(ctx):
    special = make_user("special@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx.get_engine(), special):
        assert await _require_predicate() == "ok"


@pytest.mark.asyncio
async def test_enforcement_applies_to_direct_call_not_only_http_dispatch(ctx):
    """A direct Python call (no HTTP dispatcher involved) must still be gated —
    this is the exact scenario a dispatcher-only check would silently skip."""
    regular = make_user("direct-call@grunt.example.com")
    async with ctx.context(ctx.db._session(), ctx.get_engine(), regular):
        with pytest.raises(APIError):
            await _admin_only()
