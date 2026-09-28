"""Message and notification API.

Example:
    from grunt import msgprint, throw, notify

    msgprint("Operation complete!", type="success")

    if not valid:
        throw("Invalid state", code="INVALID_STATE")

    await notify("New Request", "From client ABC", doctype="Request", doc_id="REQ-001")
"""

from typing import NoReturn

from grunt.api.context import get_session, get_user


class ApplicationError(Exception):
    """Error raised by throw() — translates to HTTP exception with message."""

    def __init__(self, message: str, code: str = "ERROR", title: str = "") -> None:
        self.message = message
        self.code = code
        self.title = title
        super().__init__(message)


def msgprint(message: str, title: str = "", msg_type: str = "info") -> None:
    """Queue a message for delivery to the frontend via WebSocket.

    Messages are collected during the request and sent as a batch
    through the user's WebSocket channel after the response is returned.

    Args:
        message: Message text
        title: Optional title
        msg_type: "success", "info", "warning", "error" (default: "info")
    """
    from grunt.api.context import add_message
    from grunt.context import _messages_ctx

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


def throw(message: str, code: str = "ERROR", title: str = "") -> NoReturn:
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
    from grunt.publish import notify as _notify

    user = get_user()
    if recipient is None:
        recipient = user.email

    await _notify(
        users=[recipient],
        subject=title,
        message=message,
        doctype=doctype or None,
        doc_id=doc_id or None,
    )


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
        roles: List of role names (default: all active users if None)
        exclude_user: Optionally exclude a user email
    """
    from grunt.notification.service import NotificationService
    from grunt.publish import notify as _notify

    session = get_session()
    svc = NotificationService()

    if roles:
        emails = await svc._resolve_role_recipients(roles, session)
    else:
        from grunt.app import grunt

        rows = await grunt.db.get_all(
            "User",
            filters={"is_active": True},
            fields=["email"],
            limit=5000,
        )
        emails = [r["email"] for r in rows if r.get("email")]

    if exclude_user:
        emails = [e for e in emails if e != exclude_user]

    if emails:
        await _notify(users=emails, subject=title, message=message)


async def queue_email(
    recipient: str,
    subject: str,
    body: str,
) -> str:
    """Queue an email for delivery.

    Inserts a Pending row into EmailQueue; the ``process_email_queue`` scheduled
    task picks it up and sends it via the default outgoing EmailAccount.

    Args:
        recipient: Recipient email address
        subject: Email subject
        body: Email body (HTML supported)

    Returns:
        The EmailQueue record id, or "" if EmailQueue has no configured account.

    Example:
        await queue_email(
            "test@example.com",
            "Invoice INV-001",
            "<h1>Invoice</h1><p>Amount: 1000 UAH</p>",
        )
    """
    from grunt.email.service import email_service

    session = get_session()
    return await email_service.queue_email(session, recipient, subject, body)
