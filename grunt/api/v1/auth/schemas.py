"""Shared auth schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, EmailStr

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserResponse(BaseModel):
    id: str | None = None
    email: str
    full_name: str
    roles: list[str] = []
    is_superadmin: bool = False
    theme: str = "system"
    avatar: str | None = None
    mfa_enabled: bool = False
    created_at: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        """Build the response from a User — always the full field set.

        Every ``/auth/*`` endpoint used to hand-list which fields to include,
        and the lists had quietly drifted (some omitted ``theme``, some
        omitted ``mfa_enabled``) — the schema's own defaults then silently
        stood in for the real value (e.g. a response after a successful MFA
        login could report ``mfa_enabled: false``). One factory, one field
        set, always the user's actual values.
        """
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_superadmin=user.is_superadmin,
            theme=user.theme,
            avatar=user.avatar,
            mfa_enabled=bool(user.mfa_enabled),
            created_at=user.created_at.isoformat() if user.created_at else None,
        )


class TokenResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    mfa_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse
    mfa_required: bool = False


class UpdateMeRequest(BaseModel):
    theme: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AddRoleRequest(BaseModel):
    role_name: str


class SetPasswordRequest(BaseModel):
    email: str
    password: str


class MfaVerifyRequest(BaseModel):
    code: str


class MfaLoginRequest(BaseModel):
    mfa_token: str
    code: str
