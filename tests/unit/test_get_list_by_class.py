from grunt.auth.doctypes.User.user import User


async def test_get_list_by_class(ctx):
    users = await User.get_list(limit=5)
    assert isinstance(users, list)
    for user in users:
        assert isinstance(user, User)
        assert user.doctype == "User"
