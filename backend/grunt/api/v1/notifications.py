"""Notification API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.notification import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendNotificationRequest(BaseModel):
    """Request body for sending a notification to users."""

    users: list[str]
    subject: str
    message: str
    doctype: str | None = None
    doc_id: str | None = None


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get notifications for the current user."""
    data = await notification_service.get_notifications(
        session, user.email, unread_only=unread_only, limit=limit, offset=offset
    )
    return {"success": True, "data": data}


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mark a notification as read."""
    await notification_service.mark_read(session, notification_id)
    await session.commit()
    return {"success": True}


@router.post("/read-all")
async def mark_all_notifications_read(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mark all notifications as read for the current user."""
    count = await notification_service.mark_all_read(session, user.email)
    await session.commit()
    return {"success": True, "count": count}


@router.get("/unread-count")
async def unread_count(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the count of unread notifications for the current user."""
    from sqlalchemy import select, func  # noqa: PLC0415
    from grunt.core.db.system_tables import GruntNotification  # noqa: PLC0415

    result = await session.execute(
        select(func.count())
        .select_from(GruntNotification)
        .where(GruntNotification.user == user.email)
        .where(GruntNotification.is_read.is_(False))
    )
    count = result.scalar() or 0
    return {"success": True, "count": count}


@router.post("/send")
async def send_notification(
    body: SendNotificationRequest,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Send a notification to one or more users programmatically.

    This endpoint wraps ``grunt.publish.notify`` for use via REST API.
    """
    from grunt.publish import notify  # noqa: PLC0415

    ids = await notify(
        users=body.users,
        subject=body.subject,
        message=body.message,
        session=session,
        doctype=body.doctype,
        doc_id=body.doc_id,
    )
    return {"success": True, "data": {"ids": ids, "count": len(ids)}}
