from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from grunt.auth.mfa import check_mfa_code
from grunt.auth.service import create_mfa_token, verify_mfa_token
from grunt.auth.doctypes.User.User import User


@pytest.fixture
def mock_user():
    user = User(
        doctype="User",
        data={
            "name": "user-123",
            "email": "test@example.com",
            "full_name": "Test User",
            "is_active": True,
            "mfa_enabled": True,
        },
    )
    return user


def test_mfa_token_flow(mock_user):
    token = create_mfa_token(mock_user)
    assert token is not None

    payload = verify_mfa_token(token)
    assert payload is not None
    assert payload["uid"] == mock_user.id
    assert payload["sub"] == mock_user.email
    assert payload["mfa_pending"] is True


def test_verify_mfa_token_invalid():
    assert verify_mfa_token("invalid-token") is None


@pytest.mark.asyncio
async def test_check_mfa_code_pyotp_available(mock_user):
    # This confirms pyotp is installed and 501 is not raised
    with patch("grunt.app.grunt.db.get_all", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [{"mfa_secret": "JBSWY3DPEHPK3PXP"}]  # Example secret

        # We don't need to verify the code logic itself here (handled by pyotp)
        # but we want to see that it doesn't raise 501
        with patch("grunt.auth.mfa.verify_totp", return_value=True):
            await check_mfa_code(mock_user, "123456")

        with patch("grunt.auth.mfa.verify_totp", return_value=False):
            with pytest.raises(HTTPException) as exc:
                await check_mfa_code(mock_user, "000000")
            assert exc.value.status_code == 401
