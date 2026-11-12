"""Realtime API mixin for GruntApp facade."""

from collections.abc import Sequence
from typing import Any

from grunt.publish import MessageType
from grunt.publish import broadcast as _broadcast
from grunt.publish import notify as _notify
from grunt.publish import publish as _publish


class RealtimeAPI:
    """Notification and websocket helper methods for GruntApp."""

    async def notify(
        self,
        *,
        users: list[str],
        subject: str,
        message: str,
        doctype: str | None = None,
        doc_id: str | None = None,
        channels: Sequence[str] = ("in_app",),
    ) -> list[str]:
        """Notify one or more users (the bell by default) - see :func:`grunt.publish.notify`."""
        return await _notify(
            users=users,
            subject=subject,
            message=message,
            doctype=doctype,
            doc_id=doc_id,
            channels=channels,
        )

    async def publish(
        self,
        user: str,
        event: str,
        data: dict[str, Any] | None = None,
        *,
        message: str | None = None,
        type: MessageType = "info",
    ) -> None:
        """Send a transient WebSocket message to a specific user (not persisted)."""
        await _publish(user=user, event=event, data=data, message=message, type=type)

    async def broadcast(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        *,
        message: str | None = None,
        type: MessageType = "info",
    ) -> None:
        """Broadcast a transient WebSocket message to all connected users."""
        await _broadcast(event=event, data=data, message=message, type=type)
