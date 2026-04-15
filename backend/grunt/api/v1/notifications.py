"""Notification API whitelisted methods."""

from __future__ import annotations
from typing import Any
import structlog
import grunt

logger = structlog.get_logger()

@grunt.whitelist()
async def list_notifications(unread_only: bool = False, page: int = 1, per_page: int = 20) -> dict[str, Any]:
    """Get notifications for the current user."""
    user = await grunt.get_current_user()
    if not user:
        grunt.throw("Authentication required", "AUTH_REQUIRED")
        
    filters: dict[str, Any] = {"user": user.email}
    if str(unread_only).lower() == "true":
        filters["is_read"] = False
        
    total = await grunt.count("Notification", filters=filters)
    data = await grunt.get_list(
        "Notification",
        filters=filters,
        page=int(page),
        limit=int(per_page),
        order_by="created_at",
        order="desc",
    )
    return {"items": data, "total": total, "page": int(page), "per_page": int(per_page)}

@grunt.whitelist()
async def mark_as_read(notification_id: str) -> bool:
    """Mark a notification as read."""
    await grunt.db.set_value("Notification", notification_id, "is_read", True)
    return True

@grunt.whitelist()
async def mark_all_as_read() -> dict[str, Any]:
    """Mark all notifications as read for the current user."""
    user = await grunt.get_current_user()
    if not user:
        grunt.throw("Authentication required", "AUTH_REQUIRED")
        
    count = await grunt.bulk_update(
        "Notification",
        filters={"user": user.email, "is_read": False},
        values={"is_read": True},
    )
    return {"count": count}

@grunt.whitelist()
async def get_unread_count() -> int:
    """Get the count of unread notifications for the current user."""
    user = await grunt.get_current_user()
    if not user:
        return 0
    return await grunt.count("Notification", filters={"user": user.email, "is_read": False})

@grunt.whitelist()
async def get_vapid_public_key() -> str | None:
    """Return the VAPID public key needed to subscribe to Web Push."""
    from grunt.core.webpush.service import webpush_service
    key = await webpush_service.get_vapid_public_key(grunt.get_engine())
    if not key:
        key = await webpush_service.ensure_vapid_keys(grunt.get_engine())
    return key

@grunt.whitelist()
async def subscribe_push(endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> bool:
    """Save a browser push subscription for the current user."""
    user = await grunt.get_current_user()
    if not user:
        grunt.throw("Authentication required", "AUTH_REQUIRED")
        
    from grunt.core.webpush.service import webpush_service
    await webpush_service.save_subscription(
        grunt.get_engine(), user.email, endpoint, p256dh, auth, user_agent
    )
    return True

@grunt.whitelist()
async def unsubscribe_push(endpoint: str) -> bool:
    """Remove a browser push subscription for the current user."""
    user = await grunt.get_current_user()
    if not user:
        grunt.throw("Authentication required", "AUTH_REQUIRED")
        
    from grunt.core.webpush.service import webpush_service
    await webpush_service.remove_subscription(grunt.get_engine(), user.email, endpoint)
    return True
