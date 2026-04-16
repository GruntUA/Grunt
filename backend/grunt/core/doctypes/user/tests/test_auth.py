"""Tests for the Auth system (migrated to whitelisted methods)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_login_me(ctx, client: AsyncClient):
    """Full flow: register → login → whoami."""
    # Register via direct API
    u = await ctx.new_doc("User", {"email": "admin@grunt.example.com", "password": "secret", "full_name": "Admin"})
    await ctx.db._session().commit()

    # Login (Keep HTTP to verify JWT generation)
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@grunt.example.com", "password": "secret"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token

    # whoami via whitelisted method directly
    from grunt.core.doctypes.user.user import User as UserController, whoami
    
    # Wrap dict in controller to support attribute access in context
    u_obj = UserController(doctype="User", data=u)
    async with ctx.context(ctx.db._session(), ctx._require_engine(), u_obj):
        me = await whoami()
        assert me["email"] == "admin@grunt.example.com"
        assert me["full_name"] == "Admin"


@pytest.mark.asyncio
async def test_first_user_is_superadmin(ctx):
    """The first registered user gets is_superadmin=True."""
    from grunt.core.doctypes.user.user import register, get_user_by_email
    from grunt.core.doctypes.user.user import SYSTEM_USER
    
    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        # First user
        await register(email="first@grunt.example.com", password="pass1", full_name="First")
        await ctx.db._session().commit()
        
        u1 = await get_user_by_email("first@grunt.example.com", ctx.db._session())
        assert u1.is_superadmin is True
        
        # Second user
        await register(email="second@grunt.example.com", password="pass2", full_name="Second")
        await ctx.db._session().commit()
        
        u2 = await get_user_by_email("second@grunt.example.com", ctx.db._session())
        assert u2.is_superadmin is False


@pytest.mark.asyncio
async def test_wrong_password_returns_401(ctx):
    """Incorrect password → authenticate() returns None."""
    from grunt.core.doctypes.user.user import create_user, authenticate
    from grunt.core.doctypes.user.user import SYSTEM_USER
    
    async with ctx.context(ctx.db._session(), ctx._require_engine(), SYSTEM_USER):
        await create_user("user@grunt.example.com", "correct", "User", ctx.db._session())
        await ctx.db._session().commit()

    result = await authenticate("user@grunt.example.com", "wrong", ctx.db._session())
    assert result is None


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client: AsyncClient):
    """An invalid JWT → 401 on whoami."""
    resp = await client.get(
        "/api/v1/method/grunt.core.doctypes.user.user.whoami",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
