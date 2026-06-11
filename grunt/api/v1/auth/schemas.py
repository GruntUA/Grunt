"""Shared auth schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


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
