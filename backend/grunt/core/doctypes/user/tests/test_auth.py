"""Tests for the Auth system (migrated to whitelisted methods)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_login_me(client: AsyncClient):
    """Full flow: register → login → GET whoami returns correct user."""
    # Register
    resp = await client.post(
        "/api/v1/method/grunt.core.doctypes.user.user.register",
        json={"email": "admin@grunt.example.com", "password": "secret", "full_name": "Admin"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["email"] == "admin@grunt.example.com"
    assert data["full_name"] == "Admin"

    # Login (remain CORE REST)
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@grunt.example.com", "password": "secret"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token

    # whoami (Whitelisted)
    resp = await client.get(
        "/api/v1/method/grunt.core.doctypes.user.user.whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    me = resp.json()["data"]
    assert me["email"] == "admin@grunt.example.com"
    assert me["full_name"] == "Admin"


@pytest.mark.asyncio
async def test_first_user_is_superadmin(client: AsyncClient):
    """The first registered user gets is_superadmin=True."""
    resp = await client.post(
        "/api/v1/method/grunt.core.doctypes.user.user.register",
        json={"email": "first@grunt.example.com", "password": "pass1", "full_name": "First"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_superadmin"] is True

    # Second user is NOT superadmin
    resp = await client.post(
        "/api/v1/method/grunt.core.doctypes.user.user.register",
        json={"email": "second@grunt.example.com", "password": "pass2", "full_name": "Second"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_superadmin"] is False


@pytest.mark.asyncio
async def test_wrong_password_returns_401(client: AsyncClient):
    """Incorrect password → 401 (via CORE REST /token)."""
    await client.post(
        "/api/v1/method/grunt.core.doctypes.user.user.register",
        json={"email": "user@grunt.example.com", "password": "correct", "full_name": "User"},
    )
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "user@grunt.example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client: AsyncClient):
    """An invalid JWT → 401 on whoami."""
    resp = await client.get(
        "/api/v1/method/grunt.core.doctypes.user.user.whoami",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
