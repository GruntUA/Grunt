"""Developer API for sending notifications and realtime messages.

This module provides the public API that app developers use from hooks,
server scripts, and background tasks to communicate with users.

Usage in app hooks::

    from grunt.publish import notify, publish, broadcast

    # Persistent notification (stored in DB + pushed via WebSocket)
    await notify(
        users=["user@example.com"],
        subject="Нове замовлення",
        message="Замовлення #123 створено",
        doctype="Order",
        doc_id="abc-123",
    )

    # Transient realtime message (WebSocket only, not stored)
    await publish(
        user="user@example.com",
        event="msgprint",
        message="Операцію виконано успішно",
        type="success",
    )

    # Broadcast to all connected users
    await broadcast(
        event="system_update",
        message="Систему буде перезавантажено через 5 хвилин",
    )

A realtime message announces a change, so it waits for the commit
(:func:`grunt.db.commit.on_commit`): sent earlier, the client reloads the old
row - or a row a rollback takes back. Outside a transaction it goes at once.
Live progress goes through :mod:`grunt.progress`, which doesn't wait.
"""

from collections.abc import Sequence
from typing import Any, Literal

from grunt.api.v1.ws import manager
from grunt.db.commit import on_commit
from grunt.i18n import _
from grunt.local import require_session
from grunt.log import log
from grunt.notification.channels import Message
from grunt.notification.delivery import deliver

MessageType = Literal["success", "error", "info", "warning"]


async def notify(
    *,
    users: list[str],
    subject: str,
    message: str,
    doctype: str | None = None,
    doc_id: str | None = None,
    channels: Sequence[str] = ("in_app",),
) -> list[str]:
    """Notify one or more users - through the notification dispatcher, so each
    delivery lands in the ``NotificationDelivery`` log.

    Default channel ``in_app``: a bell row (``NotificationLog``) plus a realtime
    ping after the commit. Add ``"web_push"`` / ``"email"`` (or an app's
    channel) to reach the user outside the desk too.

    Requires an active grunt context (session + user). This is automatically
    satisfied inside request handlers, lifecycle hooks, and background tasks
    that use :meth:`grunt.local`.

    Returns:
        The names of the bell rows created.
    """
    report = await deliver(
        require_session(),
        users,
        Message(subject=subject, body=message, ref_doctype=doctype, doc_id=doc_id),
        channels,
    )
    log.info("publish.notify", users=users, subject=subject, count=report.delivered)
    return report.notification_logs


async def publish(
    *,
    user: str,
    event: str,
    message: str | None = None,
    type: MessageType = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """Send a transient realtime message to a specific user via WebSocket.

    This is NOT stored in the database - it's a one-time push.
    Use for toasts, alerts, progress updates, etc.

    Args:
        user: User email to send to.
        event: Event name (e.g. "msgprint", "notification", "progress").
        message: Message text (convenience - also added to data).
        type: Message type for UI styling: "success", "error", "info", "warning".
        data: Arbitrary payload dict.
    """
    payload: dict[str, Any] = {
        "event": event,
        "data": {
            **(data or {}),
            "type": type,
        },
    }
    if message is not None:
        payload["data"]["message"] = message

    async def send() -> None:
        try:
            await manager.send_to_user(user, payload)
        except Exception:
            log.debug("publish.ws_send_failed", user=user, ws_event=event)

    on_commit(send)


async def broadcast(
    *,
    event: str,
    message: str | None = None,
    type: MessageType = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """Broadcast a transient realtime message to ALL connected users.

    Args:
        event: Event name.
        message: Message text.
        type: Message type for UI styling.
        data: Arbitrary payload dict.
    """
    payload: dict[str, Any] = {
        "event": event,
        "data": {
            **(data or {}),
            "type": type,
        },
    }
    if message is not None:
        payload["data"]["message"] = message

    async def send() -> None:
        try:
            await manager.broadcast_all_users(payload)
        except Exception:
            log.debug("publish.broadcast_failed", ws_event=event)

    on_commit(send)


async def publish_channel(
    *,
    channel: str,
    event: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Broadcast to a public (unauthenticated) WebSocket channel.

    Public channels are used for displays, kiosks, and other screens that
    don't require login. The channel name is prefixed with ``public:``.

    Usage::

        await publish_channel(
            channel="queue:board",
            event="ticket_called",
            data={"ticket_number": "A001", "window": 3, "sound": "chime"},
        )

    Args:
        channel: Channel name (e.g. "queue:board"). ``public:`` prefix is added automatically.
        event: Event name for the frontend to handle.
        data: Arbitrary payload dict.
    """
    full_channel = f"public:{channel}"

    async def send() -> None:
        try:
            await manager.broadcast(full_channel, event, data or {})
        except Exception:
            log.debug("publish.channel_failed", channel=channel, ws_event=event)

    on_commit(send)


async def msgprint(
    *,
    user: str,
    message: str,
    title: str | None = None,
    indicator: str | None = None,
) -> None:
    """Show a message dialog to the user (mirrors the client-side `grunt.msgprint`).

    Args:
        user: User email.
        message: Message text (supports HTML).
        title: Optional dialog title.
        indicator: Color indicator ("green", "red", "orange", "blue").
    """
    await publish(
        user=user,
        event="msgprint",
        data={
            "message": message,
            "title": title,
            "indicator": indicator,
        },
    )


async def show_alert(
    *,
    user: str,
    message: str,
    type: MessageType = "info",
) -> None:
    """Show a non-blocking toast alert (mirrors the client-side `grunt.show_alert`).

    Args:
        user: User email.
        message: Alert text.
        type: "success", "error", "info", or "warning".
    """
    await publish(user=user, event="alert", message=message, type=type)


async def show_progress(
    *,
    user: str,
    title: str,
    count: int,
    total: int,
    description: str | None = None,
    task_id: str | None = None,
) -> None:
    """Show/update a progress bar for the user (mirrors the client-side `grunt.show_progress`).

    Args:
        user: User email.
        title: Progress bar title.
        count: Current progress value.
        total: Total value.
        description: Optional description text.
        task_id: Unique task identifier - use when multiple tasks share the same title.
    """
    await publish(
        user=user,
        event="progress",
        data={
            "title": title,
            "count": count,
            "total": total,
            "description": description,
            "percent": round((count / total) * 100) if total > 0 else 0,
            **({"task_id": task_id} if task_id else {}),
        },
    )


async def throw(
    *,
    user: str,
    message: str,
    title: str | None = None,
) -> None:
    """Show an error dialog to the user (mirrors the client-side `grunt.throw`, without raising).

    Args:
        user: User email.
        message: Error message.
        title: Optional dialog title.
    """
    await publish(
        user=user,
        event="msgprint",
        type="error",
        data={
            "message": message,
            "title": title or _("Error"),
            "indicator": "red",
        },
    )
