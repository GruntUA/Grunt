"""Password reset endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import Depends, HTTPException, Request, status

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.auth.doctypes.User.user import get_user_by_email
from grunt.auth.service import (
    consume_password_reset_token,
    create_password_reset_token,
)
from grunt.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    import grunt.api.v1.auth.schemas

router = GruntRouter(optional_auth=True)


# Rate limiting is enforced by RateLimitMiddleware (see _AUTH_STRICT_PATHS in
# grunt/middleware/rate_limit.py, which covers this exact path).
@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    request: Request,
    body: grunt.api.v1.auth.schemas.ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a password reset email."""
    from grunt.app import grunt

    log = structlog.get_logger()
    user = await get_user_by_email(body.email)
    if user is None:
        return ok()

    if not user.id:
        return ok()

    token = await create_password_reset_token(user.id)

    from grunt.config import settings

    reset_url = f"{settings.app_url}/reset-password?token={token}"

    try:
        from grunt.email.service import email_service

        html_body = await grunt.render_template(
            "password_reset.html",
            {"full_name": user.full_name, "reset_url": reset_url},
        )
        plain = (
            f"Привіт, {user.full_name}.\n\n"
            "Посилання для скидання пароля (дійсне 1 годину):\n\n"
            f"{reset_url}\n\n"
            "Якщо ви не надсилали цей запит — проігноруйте цей лист."
        )
        await email_service.queue_email(
            session=session,
            to=user.email,
            subject="Скидання пароля",
            body=plain,
            html_body=html_body,
        )
        await session.flush()
        log.info("auth.forgot_password", email=user.email)
    except Exception:
        log.warning("auth.forgot_password_email_queue_failed", email=user.email)

    return ok()


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    body: grunt.api.v1.auth.schemas.ResetPasswordRequest,
) -> dict:
    """Reset password using a valid token."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    reset_ok = await consume_password_reset_token(body.token, body.new_password)
    if not reset_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    return ok()
