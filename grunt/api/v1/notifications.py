"""Notification API whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt.i18n import _


@grunt.whitelist()
async def list_notifications(
    unread_only: bool = False, page: int = 1, per_page: int = 20
) -> dict[str, Any]:
    """Get notifications for the current user."""
    user = await grunt.get_current_user()
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
    """Mark a notification as read — only if it belongs to the current user."""
    user = await grunt.get_current_user()
    count = await grunt.db.bulk_update(
        "Notification",
        filters={"name": notification_id, "user": user.email},
        values={"is_read": True},
    )
    return count > 0


@grunt.whitelist()
async def mark_all_as_read() -> dict[str, Any]:
    """Mark all notifications as read for the current user."""
    user = await grunt.get_current_user()
    count = await grunt.db.bulk_update(
        "Notification",
        filters={"user": user.email, "is_read": False},
        values={"is_read": True},
    )
    return {"count": count}


@grunt.whitelist()
async def get_unread_count() -> int:
    """Get the count of unread notifications for the current user."""
    user = await grunt.get_current_user()
    return await grunt.count("Notification", filters={"user": user.email, "is_read": False})


@grunt.whitelist()
async def get_vapid_public_key() -> str | None:
    """Return the VAPID public key needed to subscribe to Web Push.

    ``None`` when Web Push is disabled in SystemSettings — the client then
    shows "server not configured for push".
    """
    from grunt.site.settings import get_setting
    from grunt.webpush.service import webpush_service

    if not await get_setting("enable_web_push", False):
        return None

    key = await webpush_service.get_vapid_public_key()
    if not key:
        key = await webpush_service.ensure_vapid_keys()
    return key


@grunt.whitelist()
async def subscribe_push(endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> bool:
    """Save a browser push subscription for the current user."""
    from grunt.site.settings import get_setting

    if not await get_setting("enable_web_push", False):
        grunt.throw(_("Web Push is disabled in the system settings"), "FORBIDDEN")

    user = await grunt.get_current_user()
    from grunt.webpush.service import webpush_service

    await webpush_service.save_subscription(user.email, endpoint, p256dh, auth, user_agent)
    return True


@grunt.whitelist()
async def unsubscribe_push(endpoint: str) -> bool:
    """Remove a browser push subscription for the current user."""
    user = await grunt.get_current_user()
    from grunt.webpush.service import webpush_service

    await webpush_service.remove_subscription(endpoint, user.email)
    return True
