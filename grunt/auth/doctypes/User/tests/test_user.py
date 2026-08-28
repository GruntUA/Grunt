import pytest

from grunt.auth.doctypes.User.user import User


@pytest.mark.asyncio
async def test_user_controller_full_name_and_validation():
    """full_name is built from name parts; first/last name are required."""
    user = User(
        doctype="User",
        data={
            "email": "test@example.com",
            "first_name": "Іван",
            "last_name": "Іванов",
            "middle_name": "Іванович",
        },
    )

    await user.before_save()
    assert user.full_name == "Іванов Іван Іванович"

    user.middle_name = ""
    await user.before_save()
    assert user.full_name == "Іванов Іван"

    # Required name fields are enforced by validate()
    bare = User(doctype="User", data={"email": "test@example.com"})
    with pytest.raises(ValueError, match="Ім'я є обов'язковим"):
        await bare.validate()

    bare.first_name = "Іван"
    with pytest.raises(ValueError, match="Прізвище є обов'язковим"):
        await bare.validate()

    bare.last_name = "Іванов"
    await bare.validate()  # should not raise
