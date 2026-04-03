"""Message and notification API.

Example:
    from grunt import msgprint, throw, notify

    msgprint("Operation complete!", type="success")

    if not valid:
        throw("Invalid state", code="INVALID_STATE")

    await notify("New Request", "From client ABC", doctype="Request", doc_id="REQ-001")
"""

from typing import Any

import structlog

from grunt.api.context import get_session, get_user

logger = structlog.get_logger()


class ApplicationError(Exception):
    """Error raised by throw() — translates to HTTP exception with message."""

    def __init__(self, message: str, code: str = "ERROR", title: str = "") -> None:
        self.message = message
        self.code = code
        self.title = title
        super().__init__(message)


def msgprint(message: str, title: str = "", msg_type: str = "info") -> None:
    """Queue a message for the current request response.

    Messages are collected and returned to the frontend in the response.

    Args:
        message: Message text
        title: Optional title
        msg_type: "success", "info", "warning", "error" (default: "info")
    """
    # TODO: Implement message queue in request context
    # For now, just log
    logger.info("msgprint", message=message, title=title, type=msg_type)


def msgprint_list(items: list[str], title: str = "") -> None:
    """Queue a list of messages.

    Args:
        items: List of message strings
        title: Optional list title
    """
    for item in items:
        msgprint(item, title=title, msg_type="info")


def throw(message: str, code: str = "ERROR", title: str = "") -> None:
    """Raise an ApplicationError (translates to HTTP exception + message).

    This stops execution and returns an error response to the frontend.

    Args:
        message: Error message shown to user
        code: Error code (e.g., "VALIDATION_ERROR", "PERMISSION_DENIED")
        title: Optional error title

    Raises:
        ApplicationError
    """
    raise ApplicationError(message, code=code, title=title)


async def notify(
    title: str,
    message: str,
    doctype: str = "",
    doc_id: str = "",
    icon: str = "info",
    recipient: str | None = None,
) -> None:
    """Send an in-app notification to a user.

    Args:
        title: Notification title
        message: Notification body
        doctype: Optional document type (e.g., "Request")
        doc_id: Optional document ID (links to the document)
        icon: Icon type (default: "info")
        recipient: Target user email (default: current user)

    Example:
        await notify(
            "New invoice",
            "Invoice INV-001 from ABC Inc",
            doctype="Invoice",
            doc_id="INV-001"
        )
    """
    session = get_session()
    user = get_user()

    if recipient is None:
        recipient = user.email

    logger.info(
        "notification.queued",
        title=title,
        message=message,
        doctype=doctype,
        doc_id=doc_id,
        recipient=recipient,
    )

    # TODO: Create Notification DocType record
    # TODO: Trigger notification delivery (in-app, email, push)


async def notify_all(
    title: str,
    message: str,
    roles: list[str] | None = None,
    exclude_user: str | None = None,
) -> None:
    """Send a notification to all users with specific roles.

    Args:
        title: Notification title
        message: Message body
        roles: List of role names (default: all users if None)
        exclude_user: Optionally exclude a user email
    """
    # TODO: Query users by roles
    # TODO: Send notify() to each in bulk
    logger.info(
        "notification.broadcast",
        title=title,
        message=message,
        roles=roles,
    )


async def queue_email(
    recipient: str,
    subject: str,
    body: str,
    doctype: str = "",
    doc_id: str = "",
) -> None:
    """Queue an email for delivery.

    Queues the email in EmailQueue for async delivery.

    Args:
        recipient: Recipient email address
        subject: Email subject
        body: Email body (HTML supported)
        doctype: Optional document type (for linking)
        doc_id: Optional document ID (for linking)

    Example:
        await queue_email(
            "test@example.com",
            "Invoice INV-001",
            "<h1>Invoice</h1><p>Amount: 1000 UAH</p>",
            doctype="Invoice",
            doc_id="INV-001"
        )
    """
    session = get_session()

    logger.info(
        "email.queued",
        recipient=recipient,
        subject=subject,
        doctype=doctype,
        doc_id=doc_id,
    )

    # TODO: Create EmailQueue record
    # from grunt.core.metadata.registry import doctype_registry
    # from grunt.core.metadata.compiler import compile_doctype_to_table
    # table = compile_doctype_to_table(doctype_registry._doctypes["EmailQueue"])
    # await session.execute(table.insert().values(...))
    # await session.flush()
