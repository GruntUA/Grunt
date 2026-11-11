"""``get_roles`` / ``has_roles``: a user's roles by email, as ``frappe.get_roles``."""

import pytest

from grunt.auth.constants import GUEST_USER_EMAIL, SYSTEM_USER_EMAIL
from grunt.permissions.roles import get_roles, has_roles
from tests.support import acting_as, make_user

BOB = "bob.roles@example.com"


@pytest.fixture
async def bob(ctx):
    await ctx.new_doc(
        "User",
        {
            "email": BOB,
            "first_name": "Bob",
            "last_name": "R",
            "roles": [{"role_name": "System Manager"}],
        },
    )
    return BOB


async def test_built_in_identities_without_a_database():
    assert await get_roles(SYSTEM_USER_EMAIL) == ["System Manager"]
    assert await get_roles(GUEST_USER_EMAIL) == ["Guest"]


async def test_the_context_user_answers_from_the_context():
    with acting_as(make_user("ann@example.com", ["Accounts User"])):
        assert await get_roles() == ["Accounts User"]
        assert await get_roles("ann@example.com") == ["Accounts User"]
        assert await has_roles(["Accounts User", "Other"])
        assert not await has_roles(["System Manager"])


async def test_no_user_in_context_has_no_roles():
    assert await get_roles() == []
    assert not await has_roles(["Guest"])


async def test_another_user_answers_from_their_user_role_rows(bob):
    assert await get_roles(bob) == ["System Manager"]
    assert await has_roles(["System Manager"], user=bob)


async def test_rows_are_found_through_the_user_row_not_by_email(ctx, bob):
    """``User.name`` is the email only until the document is renamed."""
    await ctx.rename_doc("User", bob, "bob-renamed")
    assert await ctx.db.get_value("User", {"email": bob}, "name") == "bob-renamed"

    assert await get_roles(bob) == ["System Manager"]


async def test_an_unknown_email_has_no_roles(ctx):
    assert await get_roles("nobody@example.com") == []
