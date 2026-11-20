import base64
import json
import re
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parsedate_to_datetime
from typing import Any

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.db.commit import on_commit
from grunt.i18n import _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.site.settings import get_setting
from grunt.storage.files import store
from grunt.tasks.broker import by_name
lazy from grunt.document.api import documents
lazy from grunt.integrations.oauth import OAuthError, get_access_token

_db = GruntDB()  # stateless: reads through the context's session

# Placeholder returned instead of a stored SMTP password on every read by a
# non-System-Manager (see grunt.email.hooks.mask_smtp_password). Saving the
# account back with
# this exact value keeps the stored password untouched
# (EmailAccount.before_save).
SMTP_PASSWORD_MASK = "••••••••"

# Outgoing ``EmailMessage`` statuses a later send attempt overwrites.
PENDING_STATUSES = ("Queued", "Error")

# ``EmailQueue.priority``: the worker sends higher first (an empty one - a row
# queued before priorities - counts as normal).
PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW = "High", "Normal", "Low"
PRIORITIES = (PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW)

# A temporary failure is tried again after these pauses (minutes); past the
# last one the letter is an error.
RETRY_DELAYS_MINUTES = (1, 5, 15, 60, 240)


def is_temporary(exc: BaseException) -> bool:
    """Whether sending may work later: no answer, a dropped connection, a 4xx
    reply, a token that could not be renewed. A 5xx (a bad address, a refused
    sign-in) and anything unexpected (likely a bug - better seen at once) are
    final."""
    if isinstance(exc, aiosmtplib.SMTPRecipientsRefused):
        return all(400 <= r.code < 500 for r in exc.recipients)
    if isinstance(exc, aiosmtplib.SMTPResponseException):
        return 400 <= exc.code < 500
    return isinstance(exc, (aiosmtplib.SMTPException, OSError, TimeoutError, OAuthError))


def split_addresses(value: str | None) -> list[str]:
    """Bare addresses from a To/Cc/Bcc header value (``"A <a@x>, b@y"``)."""
    return [addr for _name, addr in getaddresses([value or ""]) if addr]


def envelope_recipients(
    msg: EmailMessage, message: dict[str, Any], account: dict[str, Any]
) -> list[str]:
    """Everyone the letter goes to: To, Cc, its Bcc and the mailbox's ``always_bcc``."""
    seen: dict[str, None] = {}
    for value in (
        msg["To"],
        msg["Cc"],
        message.get("bcc"),
        account.get("always_bcc"),
    ):
        for addr in split_addresses(value):
            seen.setdefault(addr.lower(), None)
    return list(seen)


async def _kick_queue() -> None:
    """Best-effort nudge for the ``process_email_queue`` scheduled task."""
    try:
        await by_name("grunt.email.tasks:process_email_queue").kiq()
    except Exception:
        log.warning("email.queue_kick_failed", exc_info=True)


def uses_oauth(account: dict[str, Any]) -> bool:
    return account.get("auth_method") == "OAuth"


def oauth_user(account: dict[str, Any]) -> str:
    """Who XOAUTH2 signs in as: the account that granted access."""
    return account.get("oauth_account") or account.get("email_address") or ""


async def oauth_token(account: dict[str, Any]) -> str:
    """A fresh access token of an OAuth mailbox (may refresh and commit)."""
    return await get_access_token("EmailAccount", account["name"])


async def smtp_sign_in(
    smtp: aiosmtplib.SMTP, account: dict[str, Any], password: str | None = None
) -> None:
    """Sign *smtp* in as *account*: XOAUTH2 for OAuth, else the password if any."""
    if uses_oauth(account):
        await smtp.auth_xoauth2(oauth_user(account), await oauth_token(account))
        return
    username = account.get("smtp_user") or account.get("email_address")
    password = password if password is not None else account.get("smtp_password")
    if username and password:
        await smtp.login(username, password)


def smtp_connect_kwargs(host: str, port: int | None, use_tls: bool) -> dict[str, Any]:
    """Build ``aiosmtplib.SMTP`` kwargs with the correct TLS mode for the port.

    - ``465`` -> implicit TLS from the first byte (SMTPS).
    - ``587`` / ``25`` / other -> connect in plaintext, then upgrade via
      STARTTLS: forced when ``use_tls`` is set, best-effort otherwise.

    Passing ``use_tls=True`` on port 587 (as a naive reading of the account's
    "use TLS" checkbox suggests) makes the client start a TLS handshake against
    a plaintext SMTP banner - Gmail then fails with
    ``[SSL: WRONG_VERSION_NUMBER] wrong version number``.
    """
    port = int(port or 587)
    if port == 465:
        return {"hostname": host, "port": port, "use_tls": True}
    return {
        "hostname": host,
        "port": port,
        "use_tls": False,
        "start_tls": True if use_tls else None,
    }


class EmailService:
    """Outgoing mail (SMTP, the queue) and the ``EmailMessage`` log.

    Inbound mail (IMAP, DSN/MDN reports) lives in ``grunt.email.inbound``.
    """

    @staticmethod
    async def send_now(account: dict[str, Any], message: dict[str, Any]) -> str | None:
        """Send an email immediately using the provided account settings.

        Returns the ``EmailMessage`` the letter is logged as (None if logging failed).
        """
        if not account.get("enable_outgoing"):
            raise ValueError(
                f"Outgoing email is disabled for account {account.get('email_address')}"
            )

        smtp_server = account.get("smtp_server") or ""
        smtp_port = account.get("smtp_port", 587)
        use_tls = account.get("use_tls", True)

        # Construct EmailMessage
        msg = EmailMessage()
        msg["Subject"] = message.get("subject", "")
        msg["From"] = account.get("email_address")
        msg["To"] = message.get("recipient")
        if message.get("cc"):
            msg["Cc"] = message["cc"]
        reply_to = message.get("reply_to") or account.get("reply_to")
        if reply_to:
            msg["Reply-To"] = reply_to
        msg["Message-ID"] = message.get("message_id") or make_msgid()
        # Threading: a reply carries the letter it answers and the chain before
        # it, so the recipient's client - and our own inbox routing - can tell.
        if message.get("in_reply_to"):
            msg["In-Reply-To"] = message["in_reply_to"]
        if message.get("message_references"):
            msg["References"] = message["message_references"]

        if message.get("unsubscribe_url"):
            # One-click unsubscribe (RFC 8058) - Gmail / Yahoo ask it of bulk mail.
            msg["List-Unsubscribe"] = f"<{message['unsubscribe_url']}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        if message.get("request_receipt"):
            # Ask the recipient's client for a read receipt (MDN). Honoured only
            # by some clients and only with the user's consent - best-effort.
            receipt_addr = account.get("email_address")
            msg["Disposition-Notification-To"] = receipt_addr
            msg["Return-Receipt-To"] = receipt_addr

        content = message.get("content", "")
        if message.get("is_html") or message.get("html"):
            plain = (
                message.get("text_content")
                or message.get("text")
                or _("This message is in HTML format.")
            )
            msg.set_content(plain)
            msg.add_alternative(content, subtype="html")
        else:
            msg.set_content(content)

        for att in message.get("attachments") or []:
            data = att.get("content")
            if not data:
                continue
            mimetype = att.get("mimetype") or "application/octet-stream"
            maintype, _sep, subtype = mimetype.partition("/")
            msg.add_attachment(
                data,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=att.get("filename") or "attachment",
            )

        try:
            async with aiosmtplib.SMTP(
                **smtp_connect_kwargs(smtp_server, smtp_port, use_tls)
            ) as smtp:
                await smtp_sign_in(smtp, account)
                # Bcc (the letter's and the mailbox's ``always_bcc``) goes in
                # the envelope only - never as a header the others would see.
                await smtp.send_message(msg, recipients=envelope_recipients(msg, message, account))

            log.info(
                "email.sent", recipient=message.get("recipient"), subject=message.get("subject")
            )
        except Exception as e:
            log.error("email.send_failed", error=str(e), recipient=message.get("recipient"))
            await EmailService._log_outgoing(account, message, msg, status="Error", error=str(e))
            raise
        return await EmailService._log_outgoing(account, message, msg, status="Sent")

    @staticmethod
    async def _log_outgoing(
        account: dict[str, Any],
        message: dict[str, Any],
        msg: EmailMessage,
        *,
        status: str,
        error: str | None = None,
    ) -> str | None:
        html = bool(message.get("is_html") or message.get("html"))
        content = message.get("content", "")
        plain = message.get("text_content") or message.get("text") or None
        return await EmailService.record_message(
            direction="Outgoing",
            status=status,
            subject=message.get("subject", ""),
            sender=account.get("email_address") or "",
            recipients=message.get("recipient") or "",
            cc=message.get("cc"),
            email_account=message.get("email_account") or account.get("name"),
            body_html=content if html else None,
            body_text=plain if html else content,
            message_date=datetime.now(UTC),
            message_id=msg["Message-ID"],
            in_reply_to=message.get("in_reply_to"),
            message_references=message.get("message_references"),
            error_message=error,
            request_receipt=bool(message.get("request_receipt")),
            ref_doctype=message.get("ref_doctype"),
            ref_name=message.get("ref_name"),
            attachments=[
                {
                    "filename": a.get("filename"),
                    "size": len(a.get("content") or b""),
                    "mimetype": a.get("mimetype"),
                }
                for a in (message.get("attachments") or [])
            ],
        )

    @staticmethod
    async def store_bytes(
        content: bytes,
        filename: str,
        mimetype: str | None,
        *,
        attached_to_doctype: str | None = None,
        attached_to_id: str | None = None,
    ) -> str | None:
        """Save raw bytes through the storage backend as a private File; return its URL.

        With ``attached_to_*`` the file is also the document's attachment.
        """
        try:
            # Mail attachments are private; the UI opens them via signed URLs
            # (grunt.storage.signing).
            fdoc = await store(
                content,
                filename or "attachment",
                mimetype,
                attached_to_doctype=attached_to_doctype,
                attached_to_id=attached_to_id,
            )
            return fdoc["file_url"]
        except Exception:
            log.exception("email.store_bytes_failed")
            return None

    @staticmethod
    async def record_message(
        *,
        direction: str,
        status: str,
        subject: str = "",
        sender: str = "",
        recipients: str = "",
        email_account: str | None = None,
        cc: str | None = None,
        body_html: str | None = None,
        body_text: str | None = None,
        message_date: datetime | None = None,
        message_id: str | None = None,
        error_message: str | None = None,
        ref_doctype: str | None = None,
        ref_name: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        is_read: bool | None = None,
        request_receipt: bool = False,
        in_reply_to: str | None = None,
        message_references: str | None = None,
        is_auto_reply: bool = False,
        session: AsyncSession | None = None,
    ) -> str | None:
        """Best-effort: persist one ``EmailMessage`` row (dedup by Message-ID).

        An outgoing letter already on record as ``Queued`` or ``Error`` under
        the same Message-ID (written from a document before the queue sent it,
        or a failed try) is updated to the new status instead; any other
        duplicate is skipped (None).
        """
        try:
            sess = session or require_session()
        except RuntimeError:
            log.warning("email.record_no_session")
            return None

        mid = (message_id or "").strip() or None
        att_rows = attachments or []
        try:
            async with system_context(sess):
                if mid:
                    existing = await _db.get_value(
                        "EmailMessage", {"message_id": mid}, ["name", "status"], as_dict=True
                    )
                    if existing:
                        if direction == "Outgoing" and existing.get("status") in PENDING_STATUSES:
                            await _db.set_value(
                                "EmailMessage",
                                existing["name"],
                                {
                                    "status": status,
                                    "error_message": error_message or None,
                                    "message_date": message_date or datetime.now(UTC),
                                },
                            )
                            return str(existing["name"])
                        return None
                doc = await documents.new_doc(
                    "EmailMessage",
                    {
                        "direction": direction,
                        "status": status,
                        "subject": (subject or "")[:500],
                        "sender": sender or "",
                        "recipients": recipients or "",
                        "cc": cc or None,
                        "email_account": email_account,
                        "body_html": body_html or None,
                        "body_text": body_text or None,
                        "message_date": message_date or datetime.now(UTC),
                        "message_id": mid,
                        "error_message": error_message or None,
                        "ref_doctype": ref_doctype or None,
                        "ref_name": ref_name or None,
                        "request_receipt": bool(request_receipt),
                        "in_reply_to": (in_reply_to or "").strip() or None,
                        "message_references": (message_references or "").strip() or None,
                        "is_auto_reply": bool(is_auto_reply),
                        "has_attachments": bool(att_rows),
                        "is_read": (
                            bool(is_read) if is_read is not None else (direction == "Outgoing")
                        ),
                        "attachments": [
                            {
                                "file": a.get("file") or None,
                                "filename": a.get("filename") or "attachment",
                                "size": int(a.get("size") or 0),
                                "mimetype": a.get("mimetype") or "",
                            }
                            for a in att_rows
                        ],
                    },
                )
            return doc.get("name")
        except Exception:
            log.exception("email.record_failed")
            return None

    @staticmethod
    def parse_date(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            return parsedate_to_datetime(raw)
        except Exception:
            return None

    @staticmethod
    async def resolve_outgoing_account_id(session: AsyncSession) -> str | None:
        """The EmailAccount id outgoing mail is sent from, or None if unconfigured.

        ``SystemSettings.default_email_account`` when it points at a real account,
        otherwise the first ``EmailAccount`` with ``enable_outgoing=True``.
        """
        async with system_context(session):
            configured = await get_setting("default_email_account")
            if configured and await _db.exists("EmailAccount", {"name": configured}):
                return str(configured)
            accounts = await _db.get_all(
                "EmailAccount",
                filters={"enable_outgoing": True},
                fields=["name"],
                limit=1,
            )
            return str(accounts[0]["name"]) if accounts else None

    @staticmethod
    async def queue_email(
        session: AsyncSession,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        email_account: str | None = None,
        *,
        cc: str | None = None,
        bcc: str | None = None,
        reply_to: str | None = None,
        message_id: str | None = None,
        in_reply_to: str | None = None,
        message_references: str | None = None,
        ref_doctype: str | None = None,
        ref_name: str | None = None,
        footer: bool = True,
        priority: str = PRIORITY_NORMAL,
        send_after: datetime | None = None,
        unsubscribe_url: str | None = None,
    ) -> str:
        """Insert a record into EmailQueue for async delivery.

        ``cc`` / ``bcc`` / ``reply_to`` - extra headers (Bcc only in the
        envelope); ``message_id`` - fixed in advance (the letter is already on
        record, e.g. on a document's timeline); ``in_reply_to`` /
        ``message_references`` - the thread it answers; ``ref_doctype`` /
        ``ref_name`` - the document it is logged against. ``footer=False``
        leaves out ``SystemSettings.email_footer``. ``priority`` - ``High``
        (sign-in codes, password resets), ``Normal`` or ``Low`` (notifications,
        digests, reports); ``send_after`` - not before then;
        ``unsubscribe_url`` - the ``List-Unsubscribe`` link of a notification.

        Sending account: *email_account* when given, else
        ``SystemSettings.default_email_account`` when set, otherwise the first
        EmailAccount with ``enable_outgoing=True``.
        ``SystemSettings.email_footer`` (if any) is appended to the body.

        ``attachments`` - ``[{"filename", "mimetype", "content": bytes}]``; kept
        base64-encoded on the queue row (never as public File records).
        """
        # Resolve the outgoing account id (best-effort - None if unconfigured)
        email_account_id: str | None = None
        footer_html: str = ""
        try:
            email_account_id = email_account or await EmailService.resolve_outgoing_account_id(
                session
            )
            async with system_context(session):
                raw_footer = (await get_setting("email_footer") or "").strip()
                # Ignore markup-only footers like "<p></p>" that a rich-text
                # editor leaves behind when the field is "empty".
                if footer and re.sub(r"<[^>]+>", "", raw_footer).strip():
                    footer_html = raw_footer
        except Exception:
            log.exception("suppressed_error")

        is_html = bool(html_body)
        html_content = html_body or ""
        text_content = body
        if footer_html:
            plain_footer = re.sub(r"<[^>]+>", "", footer_html).strip()
            text_content = f"{body}\n\n{plain_footer}"
            if is_html:
                html_content = f"{html_body}<br><br>{footer_html}"

        # ``content`` is what SMTP sends as the primary body; ``text_content`` is
        # the ``text/plain`` alternative (and the fallback for HTML mail).
        content = html_content if is_html else text_content

        record_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        try:
            async with system_context(session):
                await _db.insert_one(
                    "EmailQueue",
                    {
                        "name": record_id,
                        "owner": "system",
                        "created_at": now,
                        "modified_at": now,
                        "modified_by": "system",
                        "recipient": to,
                        "subject": subject,
                        "content": content,
                        "text_content": text_content,
                        "is_html": is_html,
                        "status": "Pending",
                        "email_account": email_account_id,
                        "attachments": encode_attachments(attachments),
                        "cc": cc or None,
                        "bcc": bcc or None,
                        "reply_to": reply_to or None,
                        "message_id": message_id or None,
                        "in_reply_to": in_reply_to or None,
                        "message_references": message_references or None,
                        "ref_doctype": ref_doctype or None,
                        "ref_name": ref_name or None,
                        "priority": priority if priority in PRIORITIES else PRIORITY_NORMAL,
                        "send_after": send_after,
                        "retry": 0,
                        "unsubscribe_url": unsubscribe_url or None,
                    },
                )
        except Exception:
            log.warning("email.queue_doctype_missing")
            return ""

        # Right after the commit, not at the every-5-min tick: the row is then
        # visible to the worker, and a rollback sends nothing. One kick per
        # transaction, however many emails it queues.
        on_commit(_kick_queue, session=session, key="email.kick_queue")
        return record_id


def encode_attachments(attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """``content: bytes`` -> ``content_b64`` so attachments fit a JSON column."""
    if not attachments:
        return None
    return [
        {
            "filename": a.get("filename") or "attachment",
            "mimetype": a.get("mimetype") or "application/octet-stream",
            "content_b64": base64.b64encode(a["content"]).decode("ascii"),
        }
        for a in attachments
    ]


def decode_attachments(stored: Any) -> list[dict[str, Any]]:
    """Inverse of :func:`encode_attachments` - what :meth:`EmailService.send_now` takes."""
    if isinstance(stored, str):
        stored = json.loads(stored or "null")
    return [
        {
            "filename": a.get("filename") or "attachment",
            "mimetype": a.get("mimetype") or "application/octet-stream",
            "content": base64.b64decode(a.get("content_b64") or ""),
        }
        for a in stored or []
    ]


email_service = EmailService()
