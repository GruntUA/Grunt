import pytest

from grunt.auth.doctypes.User.user import User


@pytest.mark.asyncio
async def test_get_all_generic(ctx):
    # ctx fixture provides the grunt singleton with active context.
    # We'll use the existing User doctype which should be in memory.
    users = await ctx.get_all(User, limit=5)

    # Verify result is a list
    assert isinstance(users, list)

    if users:
        # Verify first item is an instance of User controller
        assert isinstance(users[0], User)
        assert users[0].doctype == "User"
        # Verify we can access fields
        assert hasattr(users[0], "email")
