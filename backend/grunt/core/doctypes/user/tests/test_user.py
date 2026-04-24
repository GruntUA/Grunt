import pytest
from grunt.core.doctypes.user.user import User

@pytest.mark.asyncio
async def test_user_full_name_sync():
    """Verify that full_name is correctly constructed from parts."""
    user = User(doctype="User", data={
        "email": "test@example.com",
        "first_name": "Іван",
        "last_name": "Іванов",
        "middle_name": "Іванович"
    })
    
    await user.before_save()
    assert user.full_name == "Іванов Іван Іванович"

    # Test without middle name
    user.middle_name = ""
    await user.before_save()
    assert user.full_name == "Іванов Іван"

@pytest.mark.asyncio
async def test_user_validation():
    """Verify that required name fields are validated."""
    user = User(doctype="User", data={
        "email": "test@example.com",
    })
    
    with pytest.raises(ValueError, match="Ім'я є обов'язковим"):
        await user.validate()
    
    user.first_name = "Іван"
    with pytest.raises(ValueError, match="Прізвище є обов'язковим"):
        await user.validate()
    
    user.last_name = "Іванов"
    await user.validate() # Should not raise
