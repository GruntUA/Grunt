"""Realtime API mixin for GruntApp facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.utils.app_helpers import _format_msgprint

if TYPE_CHECKING:
    from grunt.publish import MessageType
    from grunt.session import GruntSession


class RealtimeAPI:
    """Notification and websocket helper methods for GruntApp."""

    session: GruntSession

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

    async def msgprint(
        self,
        msg: str | list,
        title: str | None = None,
        *,
        indicator: str = "blue",
        as_list: bool = False,
        as_table: bool = False,
        raise_exception: type[BaseException] | None = None,
    ) -> None:
        """Show a message dialog to the current user via WebSocket."""
        formatted = _format_msgprint(msg, as_list=as_list, as_table=as_table)

        indicator_to_type: dict[str, MessageType] = {
            "blue": "info",
            "green": "success",
            "red": "error",
            "orange": "warning",
            "yellow": "warning",
        }
        msg_type = indicator_to_type.get(indicator, "info")

        await self.publish(
            user=self.session.user,
            event="msgprint",
            data={"title": title, "indicator": indicator},
            message=formatted,
            type=msg_type,
        )

        if raise_exception is not None:
            raise raise_exception(formatted)
