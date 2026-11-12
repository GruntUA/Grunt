"""Notification API whitelisted methods."""

from typing import Any

from grunt.api.context import whitelist
from grunt.auth.current import acting_user
from grunt.db.api import GruntDB
from grunt.errors import throw
from grunt.i18n import _
from grunt.site.settings import get_setting
from grunt.webpush.service import webpush_service
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session


@whitelist()
async def list_notifications(
    unread_only: bool = False, page: int = 1, per_page: int = 20
) -> dict[str, Any]:
    """Get notifications for the current user."""
    user = acting_user()
    filters: dict[str, Any] = {"user": user.email}
    if str(unread_only).lower() == "true":
        filters["is_read"] = False

    total = await documents.count("NotificationLog", filters=filters)
    data = await documents.get_list(
        "NotificationLog",
        filters=filters,
        page=int(page),
        limit=int(per_page),
        order_by="created_at",
        order="desc",
    )
    return {"items": data, "total": total, "page": int(page), "per_page": int(per_page)}


@whitelist()
async def mark_as_read(notification_id: str) -> bool:
    """Mark a notification as read - only if it belongs to the current user."""
    user = acting_user()
    count = await _db.bulk_update(
        "NotificationLog",
        filters={"name": notification_id, "user": user.email},
        values={"is_read": True},
    )
    return count > 0


@whitelist()
async def mark_all_as_read() -> dict[str, Any]:
    """Mark all notifications as read for the current user."""
    user = acting_user()
    count = await _db.bulk_update(
        "NotificationLog",
        filters={"user": user.email, "is_read": False},
        values={"is_read": True},
    )
    return {"count": count}


@whitelist()
async def get_unread_count() -> int:
    """Get the count of unread notifications for the current user."""
    user = acting_user()
    return await documents.count("NotificationLog", filters={"user": user.email, "is_read": False})


@whitelist()
async def get_vapid_public_key() -> str | None:
    """Return the VAPID public key needed to subscribe to Web Push.

    ``None`` when Web Push is disabled in SystemSettings - the client then
    shows "server not configured for push".
    """
    if not await get_setting("enable_web_push", False):
        return None

    key = await webpush_service.get_vapid_public_key()
    if not key:
        key = await webpush_service.ensure_vapid_keys()
    return key


@whitelist()
async def subscribe_push(endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> bool:
    """Save a browser push subscription for the current user."""
    if not await get_setting("enable_web_push", False):
        throw(_("Web Push is disabled in the system settings"), "FORBIDDEN")

    user = acting_user()

    await webpush_service.save_subscription(user.email, endpoint, p256dh, auth, user_agent)
    return True


@whitelist()
async def unsubscribe_push(endpoint: str) -> bool:
    """Remove a browser push subscription for the current user."""
    user = acting_user()

    await webpush_service.remove_subscription(endpoint, user.email)
    return True
