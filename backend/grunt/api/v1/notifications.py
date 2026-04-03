"""Notification API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
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
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    table = compile_doctype_to_table(doctype_registry._doctypes["Notification"])
    result = await session.execute(
        select(func.count())
        .select_from(table)
        .where(table.c.user == user.email)
        .where(table.c.is_read.is_(False))
    )
    count = result.scalar() or 0
    return {"success": True, "count": count}


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/vapid-public-key")
async def get_vapid_public_key(
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the VAPID public key needed to subscribe to Web Push."""
    from grunt.core.webpush.service import webpush_service  # noqa: PLC0415

    key = await webpush_service.get_vapid_public_key(session)
    if not key:
        key = await webpush_service.ensure_vapid_keys(session)
        if key:
            await session.commit()
    return {"success": True, "public_key": key}


@router.post("/push-subscribe")
async def push_subscribe(
    body: PushSubscribeRequest,
    request: Request,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Save a browser push subscription for the current user."""
    from grunt.core.webpush.service import webpush_service  # noqa: PLC0415

    user_agent = request.headers.get("user-agent", "")
    await webpush_service.save_subscription(
        session, user.email, body.endpoint, body.p256dh, body.auth, user_agent
    )
    return {"success": True}


@router.delete("/push-subscribe")
async def push_unsubscribe(
    body: PushSubscribeRequest,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Remove a browser push subscription."""
    from grunt.core.webpush.service import webpush_service  # noqa: PLC0415

    await webpush_service.remove_subscription(session, body.endpoint)
    return {"success": True}


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
