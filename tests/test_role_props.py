"""Role properties: ``disabled`` (stays assigned, gives nothing), ``site_only``
(no workspace when every role is site-only), ``home_page`` (first role in the
user's order that has one)."""

import pytest
from fastapi import HTTPException

from grunt.permissions.perms import user_landing, user_perms
from grunt.permissions.roles import get_roles, role_holders

BOB = "bob.props@example.com"


async def _role(ctx, name: str, **fields: object) -> None:
    await ctx.new_doc("Role", {"role_name": name, **fields})


async def _set(ctx, name: str, **fields: object) -> None:
    await ctx.save_doc("Role", name, fields)


@pytest.fixture
async def bob(ctx):
    await _role(ctx, "Clerk", permissions=["grunt.manage_desk"], home_page="/app/office")
    await _role(ctx, "Reader", home_page="/cabinet")
    await ctx.new_doc(
        "User",
        {
            "email": BOB,
            "first_name": "Bob",
            "last_name": "P",
            "roles": [{"role_name": "Clerk"}, {"role_name": "Reader"}],
        },
    )
    return BOB


async def test_disabled_role_gives_nothing_but_stays_assigned(ctx, bob):
    assert await get_roles(bob) == ["Clerk", "Reader"]
    assert "grunt.manage_desk" in await user_perms(bob)

    await _set(ctx, "Clerk", disabled=1)

    assert await get_roles(bob) == ["Reader"]
    assert "grunt.manage_desk" not in await user_perms(bob)
    assert await role_holders(["Clerk"]) == []
    user = await ctx.get_doc("User", bob)
    assert [r["role_name"] for r in user["roles"]] == ["Clerk", "Reader"]

    await _set(ctx, "Clerk", disabled=0)
    assert await get_roles(bob) == ["Clerk", "Reader"]


async def test_signed_in_user_loses_a_disabled_role(ctx, bob):
    from grunt.auth.users import get_user_by_email

    await _set(ctx, "Clerk", disabled=1)
    user = await get_user_by_email(bob)
    assert user is not None
    assert user.role_names == ["Reader"]


@pytest.mark.parametrize("role", ["System Manager", "All", "Guest"])
async def test_protected_roles_cannot_be_disabled_or_site_only(ctx, role):
    for flag in ("disabled", "site_only"):
        with pytest.raises(HTTPException):
            await _set(ctx, role, **{flag: 1})


@pytest.mark.parametrize("path", ["https://evil.example", "//evil.example", "app/hrm"])
async def test_home_page_is_a_local_path(ctx, path):
    with pytest.raises(HTTPException):
        await _role(ctx, "Odd", home_page=path)


async def test_home_page_from_the_first_role_that_has_one(ctx, bob):
    assert (await user_landing(bob)).home_page == "/app/office"
    await _set(ctx, "Clerk", home_page="")
    assert (await user_landing(bob)).home_page == "/cabinet"


async def test_site_only_when_every_role_is(ctx, bob):
    assert not (await user_landing(bob)).site_only
    await _set(ctx, "Reader", site_only=1)
    assert not (await user_landing(bob)).site_only  # Clerk still gives the workspace
    await _set(ctx, "Clerk", site_only=1)
    assert (await user_landing(bob)).site_only
    # A disabled role doesn't count either way.
    await _set(ctx, "Clerk", site_only=0, disabled=1)
    assert (await user_landing(bob)).site_only


async def test_user_without_roles_keeps_the_workspace(ctx):
    await ctx.new_doc("User", {"email": "nobody@example.com", "first_name": "N", "last_name": "R"})
    landing = await user_landing("nobody@example.com")
    assert not landing.site_only
    assert landing.home_page is None


async def test_everything_permission_keeps_the_workspace(ctx, bob):
    await _set(ctx, "Reader", site_only=1, permissions=["*"])
    await _set(ctx, "Clerk", site_only=1)
    assert not (await user_landing(bob)).site_only
