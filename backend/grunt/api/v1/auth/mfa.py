"""MFA endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from grunt.core.auth.dependencies import current_user
from grunt.core.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.api.v1.auth.schemas import MfaVerifyRequest
    from grunt.core.auth.models import GruntUser

router = APIRouter()


@router.post("/mfa/setup")
async def mfa_setup(
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Start MFA setup."""
    from grunt.core.auth.mfa import begin_mfa_setup  # noqa: PLC0415

    info = await begin_mfa_setup(user, session)
    await session.commit()
    return {"success": True, "data": info}


@router.post("/mfa/confirm")
async def mfa_confirm(
    body: MfaVerifyRequest,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Confirm MFA setup."""
    from grunt.core.auth.mfa import confirm_mfa_setup  # noqa: PLC0415

    backup_codes = await confirm_mfa_setup(user, body.code, session)
    await session.commit()
    return {"success": True, "data": {"backup_codes": backup_codes}}


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaVerifyRequest,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Verify a TOTP or backup code."""
    from grunt.core.auth.mfa import check_mfa_code  # noqa: PLC0415

    await check_mfa_code(user, body.code, session)
    await session.commit()
    return {"success": True}


@router.delete("/mfa/disable")
async def mfa_disable(
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
) -> dict:
    """Disable MFA."""
    from grunt.core.auth.mfa import disable_mfa  # noqa: PLC0415

    await disable_mfa(user, session)
    await session.commit()
    return {"success": True, "message": "MFA вимкнено"}
