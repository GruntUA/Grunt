"""Tests for RBAC permission checker (migrated integration parts)."""

from __future__ import annotations

import pytest

from grunt.metadata.doctype import DocType, DocTypePermission
from grunt.permissions.rbac import permission_checker

# No TYPE_CHECKING needed for httpx in direct tests

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
async def test_match_eval_error_denies():
    """Regression: a match expression that fails to evaluate must deny access
    (fail closed), not silently grant it. Previously any exception inside
    _eval_match (typo'd field, unsupported syntax, ...) returned True.
    """
    user = MockUser(roles=["Employee"])
    dt = _make_doctype_with_perms(
        [{"role": "Employee", "read": True, "match": "doc.this_field_does_not_exist"}]
    )
    doc = {"owner": "user@example.com"}
    assert not await permission_checker.check(user, dt, "read", doc)


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
async def test_list_users_requires_superadmin(ctx):
    """list_users requires superadmin (contextual check)."""

    from grunt.app import grunt
    from grunt.auth.doctypes.User.user import User, list_users_api

    # 1. Create a regular user
    reg_user_data = {
        "email": "regular@grunt.example.com",
        "password": "pass",
        "first_name": "Regular",
        "last_name": "User",
    }
    reg_user_doc = await ctx.new_doc("User", reg_user_data)
    await ctx.db._session().commit()

    # 2. Try to list users as regular user
    # We simulate this by changing the context user
    reg_user_obj = User(
        doctype="User", data={"email": reg_user_doc["email"], "is_superadmin": False}
    )

    from grunt.errors import APIError

    async with grunt.context(ctx.db._session(), ctx._require_engine(), reg_user_obj):
        with pytest.raises(APIError) as excinfo:
            await list_users_api()
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_superadmin(ctx):
    """list_users works for superadmin."""
    from grunt.auth.doctypes.User.user import list_users_api, register

    # Register at least one user to list
    await register(email="admin@example.com", password="pass", first_name="Admin", last_name="User")
    await ctx.db._session().commit()

    users = await list_users_api()
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_add_remove_role(ctx):
    """Superadmin can add and remove roles from users."""
    from grunt.auth.doctypes.User.user import add_role, list_users_api, remove_role

    # Register a regular user
    target_data = {
        "email": "target@grunt.example.com",
        "password": "pass",
        "first_name": "Target",
        "last_name": "User",
    }
    target_doc = await ctx.new_doc("User", target_data)
    target_id = target_doc["name"]
    await ctx.db._session().commit()

    # Add role
    await add_role(user_id=target_id, role_name="Manager")
    await ctx.db._session().commit()

    # Verify role is in user list
    users = await list_users_api()
    user_data = next(u for u in users if u["name"] == target_id)
    assert "Manager" in user_data["roles"]

    # Remove role
    await remove_role(user_id=target_id, role_name="Manager")
    await ctx.db._session().commit()

    # Verify role removed
    users = await list_users_api()
    user_data = next(u for u in users if u["name"] == target_id)
    assert "Manager" not in user_data["roles"]
