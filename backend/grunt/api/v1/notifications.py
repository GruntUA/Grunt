"""Notification API endpoints."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.app import grunt
from grunt.core.auth.dependencies import current_user, grunt_context
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

logger = structlog.get_logger()
router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class SendNotificationRequest(BaseModel):
    """Request body for sending a notification to users."""

    users: list[str]
    subject: str
    message: str
    doctype: str | None = None
    doc_id: str | None = None


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: GruntUser = Depends(current_user),
    _: None = Depends(grunt_context),
) -> dict[str, Any]:
    """Get notifications for the current user."""
    filters: dict[str, Any] = {"user": user.email}
    if unread_only:
        filters["is_read"] = False
    total = await grunt.count("Notification", filters=filters)
    data = await grunt.get_list(
        "Notification",
        filters=filters,
        page=page,
        limit=per_page,
        order_by="created_at",
        order="desc",
    )
    return {"data": data, "total": total, "page": page, "per_page": per_page}


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    _: None = Depends(grunt_context),
) -> dict[str, Any]:
    """Mark a notification as read."""
    await grunt.db.set_value("Notification", notification_id, "is_read", True)
    return {"success": True}


@router.post("/read-all")
async def mark_all_notifications_read(
    user: GruntUser = Depends(current_user),
    _: None = Depends(grunt_context),
) -> dict[str, Any]:
    """Mark all notifications as read for the current user."""
    count = await grunt.bulk_update(
        "Notification",
        filters={"user": user.email, "is_read": False},
        values={"is_read": True},
    )
    return {"success": True, "count": count}


@router.get("/unread-count")
async def unread_count(
    user: GruntUser = Depends(current_user),
    _: None = Depends(grunt_context),
) -> dict[str, Any]:
    """Get the count of unread notifications for the current user."""
    count = await grunt.count("Notification", filters={"user": user.email, "is_read": False})
    return {"success": True, "count": count}


@router.get("/vapid-public-key")
async def get_vapid_public_key(
    _: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the VAPID public key needed to subscribe to Web Push."""
    from grunt.core.webpush.service import webpush_service  # noqa: PLC0415

    key = await webpush_service.get_vapid_public_key(session)
    if not key:
        key = await webpush_service.ensure_vapid_keys(session)
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
    _: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Remove a browser push subscription."""
    from grunt.core.webpush.service import webpush_service  # noqa: PLC0415

    await webpush_service.remove_subscription(session, body.endpoint)
    return {"success": True}


@router.post("/send")
async def send_notification(
    body: SendNotificationRequest,
    _: None = Depends(grunt_context),
) -> dict[str, Any]:
    """Send a notification to one or more users programmatically."""
    ids = await grunt.notify(
        users=body.users,
        subject=body.subject,
        message=body.message,
        doctype=body.doctype,
        doc_id=body.doc_id,
    )
    return {"success": True, "data": {"ids": ids, "count": len(ids)}}
