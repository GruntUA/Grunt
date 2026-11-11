"""Messages queued for the frontend (``grunt.msgprint``).

Example:
    from grunt import msgprint, throw  # throw: grunt.errors

    msgprint("Operation complete!", type="success")

    if not valid:
        throw("Invalid state", code="INVALID_STATE")

"""

from grunt.api.context import add_message
from grunt.local import _messages_ctx


def msgprint(message: str, title: str = "", msg_type: str = "info") -> None:
    """Queue a message for delivery to the frontend via WebSocket.

    Messages are collected during the request and sent as a batch
    through the user's WebSocket channel after the response is returned.

    Args:
        message: Message text
        title: Optional title
        msg_type: "success", "info", "warning", "error" (default: "info")
    """
    if _messages_ctx.get() is None:
        _messages_ctx.set([])
    add_message(message, title=title, msg_type=msg_type)


def msgprint_list(items: list[str], title: str = "") -> None:
    """Queue a list of messages.

    Args:
        items: List of message strings
        title: Optional list title
    """
    for item in items:
        msgprint(item, title=title, msg_type="info")
