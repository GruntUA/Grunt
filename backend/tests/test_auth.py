"""Tests for the Auth system — register, login, /me."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_login_me(client: AsyncClient):
    """Full flow: register → login → GET /me returns correct user."""
    # Register
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@grunt.example.com", "password": "secret", "full_name": "Admin"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "admin@grunt.example.com"
    assert data["full_name"] == "Admin"

    # Login
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@grunt.example.com", "password": "secret"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token

    # /me
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == "admin@grunt.example.com"
    assert me["full_name"] == "Admin"


@pytest.mark.asyncio
async def test_first_user_is_superadmin(client: AsyncClient):
    """The first registered user gets is_superadmin=True."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "first@grunt.example.com", "password": "pass1", "full_name": "First"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_superadmin"] is True

    # Second user is NOT superadmin
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "second@grunt.example.com", "password": "pass2", "full_name": "Second"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_superadmin"] is False


@pytest.mark.asyncio
async def test_wrong_password_returns_401(client: AsyncClient):
    """Incorrect password → 401."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@grunt.example.com", "password": "correct", "full_name": "User"},
    )
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "user@grunt.example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client: AsyncClient):
    """An invalid JWT → 401 on /me."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401
