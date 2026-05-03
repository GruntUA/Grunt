"""Realtime API mixin for GruntApp facade."""

from __future__ import annotations

from typing import Any

from grunt.utils.app_helpers import _format_msgprint


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
        from grunt.publish import notify as _notify  # noqa: PLC0415

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
        type: str = "info",
    ) -> None:
        """Send a transient WebSocket message to a specific user (not persisted)."""
        from grunt.publish import publish as _publish  # noqa: PLC0415

        await _publish(user=user, event=event, data=data, message=message, type=type)  # type: ignore[arg-type]

    async def broadcast(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        *,
        message: str | None = None,
        type: str = "info",
    ) -> None:
        """Broadcast a transient WebSocket message to all connected users."""
        from grunt.publish import broadcast as _broadcast  # noqa: PLC0415

        await _broadcast(event=event, data=data, message=message, type=type)  # type: ignore[arg-type]

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

        indicator_to_type = {
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
