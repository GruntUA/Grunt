"""Tests for RBAC permission checker (migrated integration parts)."""

from __future__ import annotations
from typing import TYPE_CHECKING
import pytest

from grunt.core.metadata.doctype import DocType, DocTypePermission
from grunt.core.permissions.rbac import permission_checker

if TYPE_CHECKING:
    from httpx import AsyncClient

# ── Unit tests for PermissionChecker ─────────────────────────────────────

class MockUser:
    email = "user@example.com"
    is_superadmin = False
    roles: list[str] = []

    def __init__(self, roles=None, is_superadmin=False):
        self.roles = roles or []
        self.is_superadmin = is_superadmin


def _make_doctype_with_perms(perms: list[dict]) -> DocType:
    return DocType(
        name="TestDoc",
        label="Test",
        module="test",
        fields=[],
        permissions=[DocTypePermission(**p) for p in perms],
    )


@pytest.mark.asyncio
async def test_superadmin_always_allowed():
    """Superadmin bypasses all permission checks."""
    user = MockUser(is_superadmin=True)
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_no_permissions_means_open():
    """DocType with no permissions is open to all."""
    user = MockUser()
    dt = DocType(name="Open", label="Open", module="x", fields=[])
    assert await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_role_read_allowed():
    """User with correct role can read."""
    user = MockUser(roles=["Manager"])
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_wrong_role_denied():
    """User without required role is denied."""
    user = MockUser(roles=["Viewer"])
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert not await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_all_role_always_matches():
    """'All' role matches any user."""
    user = MockUser(roles=[])
    dt = _make_doctype_with_perms([{"role": "All", "read": True}])
    assert await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_match_owner_eq_user():
    """Row-level match 'owner == user' works."""
    user = MockUser(roles=["Employee"])
    dt = _make_doctype_with_perms([{"role": "Employee", "read": True, "match": "owner == user"}])
    doc_own = {"owner": "user@example.com"}
    doc_other = {"owner": "other@example.com"}
    assert await permission_checker.check(user, dt, "read", doc_own)
    assert not await permission_checker.check(user, dt, "read", doc_other)


@pytest.mark.asyncio
async def test_require_raises_on_deny():
    """require() raises HTTPException when denied."""
    from fastapi import HTTPException
    user = MockUser(roles=[])
    dt = _make_doctype_with_perms([{"role": "Admin", "read": True}])
    with pytest.raises(HTTPException) as exc_info:
        await permission_checker.require(user, dt, "read")
    assert exc_info.value.status_code == 403


# ── Integration: role management API (Migrated) ──────────────────────────


@pytest.mark.asyncio
async def test_list_users_requires_superadmin(client: AsyncClient, auth_headers: dict):
    """list_users requires superadmin."""
    # Register a regular user
    await client.post(
        "/api/v1/method/grunt.api.v1.user.register",
        json={"email": "regular@grunt.example.com", "password": "pass", "full_name": "Regular"},
    )
    resp_login = await client.post(
        "/api/v1/auth/token",
        data={"username": "regular@grunt.example.com", "password": "pass"},
    )
    regular_token = resp_login.json()["access_token"]

    resp = await client.get(
        "/api/v1/method/grunt.api.v1.user.list_users",
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_superadmin(client: AsyncClient, auth_headers: dict):
    """list_users works for superadmin."""
    resp = await client.get("/api/v1/method/grunt.api.v1.user.list_users", headers=auth_headers)
    assert resp.status_code == 200
    users = resp.json()["data"]
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_add_remove_role(client: AsyncClient, auth_headers: dict):
    """Superadmin can add and remove roles from users."""
    # Register a regular user
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.user.register",
        json={"email": "target@grunt.example.com", "password": "pass", "full_name": "Target"},
    )
    target_id = resp.json()["data"]["id"]

    # Add role
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.user.add_role",
        json={"user_id": target_id, "role_name": "Manager"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify role is in user list
    users_resp = await client.get("/api/v1/method/grunt.api.v1.user.list_users", headers=auth_headers)
    user_data = next(u for u in users_resp.json()["data"] if u["id"] == target_id)
    assert "Manager" in user_data["roles"]

    # Remove role
    resp = await client.post(
        "/api/v1/method/grunt.api.v1.user.remove_role",
        json={"user_id": target_id, "role_name": "Manager"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify role removed
    users_resp = await client.get("/api/v1/method/grunt.api.v1.user.list_users", headers=auth_headers)
    user_data = next(u for u in users_resp.json()["data"] if u["id"] == target_id)
    assert "Manager" not in user_data["roles"]
