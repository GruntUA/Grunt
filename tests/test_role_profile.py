"""RoleProfile: a user with a profile gets its roles; manual roles stay; a
change of the profile reaches every user holding it; only user managers may
hand out profiles (test_auth.py, test_self_edit_scope); signing up can grant a default profile."""

import pytest
from fastapi import HTTPException

from grunt.permissions.roles import get_roles

BOB = "bob.profile@example.com"


async def _rows(ctx, user: str) -> list[tuple[str, str | None]]:
    doc = await ctx.get_doc("User", user)
    return [(r["role_name"], r.get("role_profile") or None) for r in doc["roles"]]


@pytest.fixture
async def clerk(ctx):
    for role in ("Clerk", "Reader", "Archivist"):
        await ctx.new_doc("Role", {"role_name": role})
    await ctx.new_doc(
        "RoleProfile",
        {"profile_name": "Office", "roles": [{"role_name": "Clerk"}, {"role_name": "Reader"}]},
    )
    await ctx.new_doc(
        "User",
        {
            "email": BOB,
            "first_name": "Bob",
            "last_name": "P",
            "roles": [{"role_name": "Archivist"}],
            "role_profiles": [{"role_profile": "Office"}],
        },
    )
    return BOB


async def test_profile_adds_its_roles_after_the_manual_ones(ctx, clerk):
    assert await _rows(ctx, clerk) == [
        ("Archivist", None),
        ("Clerk", "Office"),
        ("Reader", "Office"),
    ]
    assert await get_roles(clerk) == ["Archivist", "Clerk", "Reader"]


async def test_a_role_held_by_hand_is_not_doubled(ctx, clerk):
    await ctx.save_doc(
        "User",
        clerk,
        {
            "roles": [{"role_name": "Archivist"}, {"role_name": "Reader"}],
            "role_profiles": [{"role_profile": "Office"}],
        },
    )
    assert await _rows(ctx, clerk) == [
        ("Archivist", None),
        ("Reader", None),
        ("Clerk", "Office"),
    ]


async def test_changing_the_profile_changes_its_users(ctx, clerk):
    await ctx.save_doc(
        "RoleProfile", "Office", {"roles": [{"role_name": "Clerk"}, {"role_name": "Archivist"}]}
    )
    # Archivist is held by hand already; Reader went away with the profile.
    assert await _rows(ctx, clerk) == [("Archivist", None), ("Clerk", "Office")]


async def test_taking_the_profile_away_keeps_manual_roles(ctx, clerk):
    await ctx.save_doc("User", clerk, {"role_profiles": []})
    assert await _rows(ctx, clerk) == [("Archivist", None)]


async def test_profile_rows_rebuild_even_if_edited_in_the_form(ctx, clerk):
    doc = await ctx.get_doc("User", clerk)
    roles = [{**r, "role_name": "Archivist"} if r.get("role_profile") else r for r in doc["roles"]]
    await ctx.save_doc("User", clerk, {"roles": roles})
    assert await _rows(ctx, clerk) == [
        ("Archivist", None),
        ("Clerk", "Office"),
        ("Reader", "Office"),
    ]


async def test_profile_with_scoped_role(ctx, clerk):
    await ctx.save_doc(
        "RoleProfile",
        "Office",
        {"roles": [{"role_name": "Clerk", "scope_doctype": "Role", "scope_value": "Reader"}]},
    )
    doc = await ctx.get_doc("User", clerk)
    scoped = [r for r in doc["roles"] if r.get("role_profile")]
    assert [(r["role_name"], r["scope_doctype"], r["scope_value"]) for r in scoped] == [
        ("Clerk", "Role", "Reader")
    ]


async def test_scope_needs_both_parts(ctx, clerk):
    with pytest.raises(HTTPException):
        await ctx.save_doc(
            "RoleProfile", "Office", {"roles": [{"role_name": "Clerk", "scope_doctype": "Role"}]}
        )


async def test_assigned_profile_cannot_be_deleted(ctx, clerk):
    with pytest.raises(HTTPException):
        await ctx.delete_doc("RoleProfile", "Office")
    await ctx.save_doc("User", clerk, {"role_profiles": []})
    await ctx.delete_doc("RoleProfile", "Office")


async def test_sign_up_gets_the_default_profile(ctx, clerk):
    from grunt.auth.users import _assign_default_role

    await ctx.save_doc(
        "SystemSettings",
        "SystemSettings",
        {"allow_user_registration": 1, "default_role_profile": "Office"},
    )
    await ctx.new_doc("User", {"email": "new@example.com", "first_name": "N", "last_name": "U"})
    await _assign_default_role("new@example.com")
    assert await _rows(ctx, "new@example.com") == [("Clerk", "Office"), ("Reader", "Office")]


async def test_a_manual_role_for_a_period_keeps_the_profile_grant(ctx, clerk):
    """When the manual row lapses, the profile's grant is still stored."""
    await ctx.save_doc(
        "User",
        clerk,
        {
            "roles": [
                {"role_name": "Archivist"},
                {"role_name": "Clerk", "valid_from": "2020-01-01", "valid_to": "2020-12-31"},
            ],
            "role_profiles": [{"role_profile": "Office"}],
        },
    )
    assert await _rows(ctx, clerk) == [
        ("Archivist", None),
        ("Clerk", None),
        ("Clerk", "Office"),
        ("Reader", "Office"),
    ]
    assert await get_roles(clerk) == ["Archivist", "Clerk", "Reader"]


async def test_self_edit_cannot_take_a_role_off_its_profile(ctx, clerk):
    """Echoing the form back is fine; dropping ``role_profile`` from a row (so
    it would outlive the profile) or listing a profile twice changes nothing
    the user may change."""
    from grunt.auth.doctypes.User.user import User

    stored = (await ctx.get_doc("User", clerk))["roles"]
    await ctx.db._session().commit()
    me = User(**{"email": clerk, "name": clerk, "roles": []})
    async with ctx.context(ctx.db._session(), ctx.get_engine(), me):
        await ctx.save_doc(
            "User",
            clerk,
            {"roles": stored, "role_profiles": [{"role_profile": "Office"}] * 2},
        )
        stripped = [{**r, "role_profile": None} for r in stored]
        with pytest.raises(HTTPException) as exc:
            await ctx.save_doc("User", clerk, {"roles": stripped})
        assert exc.value.status_code == 403
