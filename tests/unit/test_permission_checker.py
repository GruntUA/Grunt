"""Tests for RBAC permission checker (migrated integration parts)."""

from __future__ import annotations

import pytest

from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocPermission
from grunt.permissions.rbac import permission_checker
from tests.support import make_user

# No TYPE_CHECKING needed for httpx in direct tests

# ── Unit tests for PermissionChecker ─────────────────────────────────────


def _make_doctype_with_perms(perms: list[dict]) -> DocType:
    return DocType(
        name="TestDoc",
        label="Test",
        module="test",
        fields=[],
        permissions=[DocPermission(**p) for p in perms],
    )


@pytest.mark.asyncio
async def test_system_user_always_allowed():
    """The internal SYSTEM_USER identity bypasses all permission checks — a
    human holding "System Manager" is scoped by matching rows like anyone
    else (see test_sensitive_doctype_permissions / test_readonly_log_doctypes,
    where several DocTypes deliberately don't grant write to System Manager)."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert await permission_checker.check(SYSTEM_USER, dt, "read")


@pytest.mark.asyncio
async def test_system_manager_without_matching_row_denied():
    """Holding "System Manager" doesn't bypass a DocType whose permissions
    don't name it — only a matching permission row grants access."""
    user = make_user("user@example.com", is_superadmin=True)
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert not await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_no_permissions_means_closed():
    """DocType with no permissions is closed to everyone but the internal
    SYSTEM_USER identity — deny-by-default: no rows means nobody has been
    granted access yet."""
    user = make_user("user@example.com")
    dt = DocType(name="Closed", label="Closed", module="x", fields=[])
    assert not await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_role_read_allowed():
    """User with correct role can read."""
    user = make_user("user@example.com", roles=["Manager"])
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_wrong_role_denied():
    """User without required role is denied."""
    user = make_user("user@example.com", roles=["Viewer"])
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert not await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_all_role_always_matches():
    """'All' role matches any user."""
    user = make_user("user@example.com", roles=[])
    dt = _make_doctype_with_perms([{"role": "All", "read": True}])
    assert await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_match_owner_eq_user():
    """Row-level match 'owner == user' works."""
    user = make_user("user@example.com", roles=["Employee"])
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
    user = make_user("user@example.com", roles=["Employee"])
    dt = _make_doctype_with_perms(
        [{"role": "Employee", "read": True, "match": "doc.this_field_does_not_exist"}]
    )
    doc = {"owner": "user@example.com"}
    assert not await permission_checker.check(user, dt, "read", doc)


@pytest.mark.asyncio
async def test_select_granted_explicitly():
    """A role with only ``select`` can select but not read."""
    user = make_user("user@example.com", roles=["Picker"])
    dt = _make_doctype_with_perms([{"role": "Picker", "select": True}])
    assert await permission_checker.check(user, dt, "select")
    assert not await permission_checker.check(user, dt, "read")


@pytest.mark.asyncio
async def test_read_implies_select():
    """A role with ``read`` implicitly satisfies ``select`` too."""
    user = make_user("user@example.com", roles=["Manager"])
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert await permission_checker.check(user, dt, "select")


@pytest.mark.asyncio
async def test_select_denied_without_grant():
    user = make_user("user@example.com", roles=["Viewer"])
    dt = _make_doctype_with_perms([{"role": "Manager", "read": True}])
    assert not await permission_checker.check(user, dt, "select")


@pytest.mark.asyncio
async def test_require_raises_on_deny():
    """require() raises HTTPException when denied."""
    from fastapi import HTTPException

    user = make_user("user@example.com", roles=[])
    dt = _make_doctype_with_perms([{"role": "Admin", "read": True}])
    with pytest.raises(HTTPException) as exc_info:
        await permission_checker.require(user, dt, "read")
    assert exc_info.value.status_code == 403


# ── Integration: role management API (Migrated) ──────────────────────────


@pytest.mark.asyncio
async def test_list_users_requires_system_manager(ctx):
    """list_users requires the System Manager role (contextual check)."""

    import grunt
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
    reg_user_obj = User(doctype="User", data={"email": reg_user_doc["email"], "roles": []})

    from grunt.errors import APIError

    async with grunt.context(ctx.db._session(), ctx.get_engine(), reg_user_obj):
        with pytest.raises(APIError) as excinfo:
            await list_users_api()
        assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_system_manager(ctx):
    """list_users works for System Manager."""
    from grunt.auth.doctypes.User.user import list_users_api, register

    # Register at least one user to list
    await register(email="admin@example.com", password="pass", first_name="Admin", last_name="User")
    await ctx.db._session().commit()

    users = await list_users_api()
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_user_roles_child_table(ctx):
    """Roles are managed through the ``User.roles`` child table."""
    from grunt.auth.doctypes.User.user import list_users_api

    await ctx.new_doc("Role", {"role_name": "Manager"})
    target_data = {
        "email": "target@grunt.example.com",
        "password": "pass",
        "first_name": "Target",
        "last_name": "User",
    }
    target_doc = await ctx.new_doc("User", target_data)
    target_id = target_doc["name"]
    await ctx.db._session().commit()

    # Assign a role
    await ctx.save_doc("User", target_id, {"roles": [{"role_name": "Manager"}]})
    await ctx.db._session().commit()

    users = await list_users_api()
    user_data = next(u for u in users if u["name"] == target_id)
    assert "Manager" in user_data["roles"]

    # Clear roles
    await ctx.save_doc("User", target_id, {"roles": []})
    await ctx.db._session().commit()

    users = await list_users_api()
    user_data = next(u for u in users if u["name"] == target_id)
    assert "Manager" not in user_data["roles"]


@pytest.mark.asyncio
async def test_count_respects_permissions(ctx):
    """`grunt.count(..., respect_permissions=True)` applies the same row-level
    `match` filter as the list view — a non-privileged user counting `User`
    sees only their own row, not everyone's."""
    import grunt
    from grunt.auth.doctypes.User.user import User, create_user

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await create_user("boss@grunt.example.com", "Str0ngPass", "Boss", "One", None)
        me = await create_user("countme@grunt.example.com", "Str0ngPass", "Count", "Me", None)
        await ctx.db._session().commit()
        raw_total = await grunt.count("User")
    assert raw_total >= 2

    me_ctx = User(
        doctype="User",
        data={"email": me.id, "name": me.id, "roles": []},
    )
    async with ctx.context(ctx.db._session(), ctx.get_engine(), me_ctx):
        assert await grunt.count("User", respect_permissions=True) == 1
        assert await grunt.count("User") == raw_total  # default path unchanged
