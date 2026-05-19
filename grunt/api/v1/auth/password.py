"""Password reset endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from grunt.api.v1.schemas.response import ok
from grunt.auth.doctypes.User.user import get_user_by_email
from grunt.auth.service import (
    consume_password_reset_token,
    create_password_reset_token,
)
from grunt.db.session import get_session
from grunt.middleware.rate_limit import limiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.api.v1.auth.schemas import (
        ForgotPasswordRequest,
        ResetPasswordRequest,
    )

router = APIRouter()


def _rate_limit(limit: str):
    """Decorator for rate limiting."""

    def decorator(func):
        if limiter is not None:
            return limiter.limit(limit)(func)
        return func

    return decorator


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@_rate_limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a password reset email."""
    log = structlog.get_logger()
    user = await get_user_by_email(body.email, session)
    if user is None:
        return ok()

    if not user.id:
        return ok()

    token = await create_password_reset_token(user.id, session)

    from grunt.config import settings  # noqa: PLC0415

    reset_url = f"{settings.app_url}/reset-password?token={token}"

    try:
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.email.service import email_service  # noqa: PLC0415

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
    except Exception:  # noqa: BLE001
        log.warning("auth.forgot_password_email_queue_failed", email=user.email)

    return ok()


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reset password using a valid token."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    reset_ok = await consume_password_reset_token(body.token, body.new_password, session)
    if not reset_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    return ok()
