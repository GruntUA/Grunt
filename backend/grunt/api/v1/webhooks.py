"""Webhook management endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/outgoing/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send a test payload for an outgoing webhook and return the delivery log."""
    from grunt.core.webhook.service import webhook_service  # noqa: PLC0415

    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can test webhooks",
        )

    result = await webhook_service.test_delivery(session, webhook_id, user.email)
    return {"success": True, "data": result}
