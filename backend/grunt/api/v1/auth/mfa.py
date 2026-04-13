"""MFA endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.core.auth.dependencies import current_user

if TYPE_CHECKING:

    from grunt.api.v1.auth.schemas import MfaVerifyRequest
    from grunt.core.auth.models import GruntUser

router = GruntRouter()


@router.post("/mfa/setup")
async def mfa_setup(
    user: GruntUser = Depends(current_user),
) -> dict:
    """Start MFA setup."""
    from grunt.core.auth.mfa import begin_mfa_setup  # noqa: PLC0415

    info = await begin_mfa_setup(user, grunt._require_session())
    return ok(info)


@router.post("/mfa/confirm")
async def mfa_confirm(
    body: MfaVerifyRequest,
    user: GruntUser = Depends(current_user),
) -> dict:
    """Confirm MFA setup."""
    from grunt.core.auth.mfa import confirm_mfa_setup  # noqa: PLC0415

    backup_codes = await confirm_mfa_setup(user, body.code, grunt._require_session())
    return ok({"backup_codes": backup_codes})


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaVerifyRequest,
    user: GruntUser = Depends(current_user),
) -> dict:
    """Verify a TOTP or backup code."""
    from grunt.core.auth.mfa import check_mfa_code  # noqa: PLC0415

    await check_mfa_code(user, body.code, grunt._require_session())
    return ok()


@router.delete("/mfa/disable")
async def mfa_disable(
    user: GruntUser = Depends(current_user),
) -> dict:
    """Disable MFA."""
    from grunt.core.auth.mfa import disable_mfa  # noqa: PLC0415

    await disable_mfa(user, grunt._require_session())
    return ok(message="MFA вимкнено")
