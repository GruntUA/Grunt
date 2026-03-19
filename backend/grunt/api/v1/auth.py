"""Auth API endpoints — register, login, me."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.auth.service import authenticate, create_access_token, create_user, get_user_by_email
from grunt.core.db.session import get_session

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    roles: list[str] = []
    is_superadmin: bool = False
    created_at: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Register a new user.  The first user automatically becomes superadmin."""
    existing = await get_user_by_email(body.email, session)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )
    user = await create_user(body.email, body.password, body.full_name, session)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """OAuth2 password grant — return access token."""
    user = await authenticate(form_data.username, form_data.password, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_superadmin=user.is_superadmin,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: GruntUser = Depends(current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
        is_superadmin=user.is_superadmin,
    )
