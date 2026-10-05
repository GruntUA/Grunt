"""Realtime API mixin for GruntApp facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grunt.publish import MessageType


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
        push: bool = True,
    ) -> list[str]:
        """Create persistent bell notifications for one or more users."""
        from grunt.publish import notify as _notify

        return await _notify(
            users=users,
            subject=subject,
            message=message,
            doctype=doctype,
            doc_id=doc_id,
            push=push,
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
        from grunt.publish import publish as _publish

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
        from grunt.publish import broadcast as _broadcast

        await _broadcast(event=event, data=data, message=message, type=type)
