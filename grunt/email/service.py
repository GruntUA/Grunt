import asyncio
import base64
import json
import re
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import make_msgid, parsedate_to_datetime
from typing import Any

import aiosmtplib
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import _, log
from grunt.site.settings import get_setting
from grunt.storage import store

# Placeholder returned instead of a stored SMTP password on every read by a
# non-System-Manager (see grunt.email.hooks.mask_smtp_password). Saving the
# account back with
# this exact value keeps the stored password untouched
# (EmailAccount.before_save).
SMTP_PASSWORD_MASK = "••••••••"

# Strong refs to in-flight "kick the queue" tasks so asyncio doesn't GC them
# before they run (see _kick_queue_after_commit).
_pending_kicks: set[asyncio.Task[Any]] = set()


async def _kick_queue() -> None:
    """Best-effort nudge for the ``process_email_queue`` scheduled task."""
    try:
        from grunt.email.tasks import process_email_queue

        await process_email_queue.kiq()
    except Exception:
        log.warning("email.queue_kick_failed", exc_info=True)


def _kick_queue_after_commit(session: AsyncSession) -> None:
    """Arm a one-shot hook that runs ``process_email_queue`` the moment this
    session's transaction commits.

    Queuing on its own leaves the row waiting for the every-5-min scheduled
    tick. Firing on ``after_commit`` (rather than right away) means the row is
    already visible to the worker's own session, and a caller that rolls back
    never triggers a send. Repeated ``queue_email`` calls in one transaction
    share a single hook.
    """

    sync_session = session.sync_session
    if sync_session.info.get("grunt_email_kick_armed"):
        return
    sync_session.info["grunt_email_kick_armed"] = True

    def _on_commit(_s: Any) -> None:
        sync_session.info["grunt_email_kick_armed"] = False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(_kick_queue())
        _pending_kicks.add(task)
        task.add_done_callback(_pending_kicks.discard)

    event.listen(sync_session, "after_commit", _on_commit, once=True)


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
    async def send_now(account: dict[str, Any], message: dict[str, Any]) -> None:
        """Send an email immediately using the provided account settings."""
        if not account.get("enable_outgoing"):
            raise ValueError(
                f"Outgoing email is disabled for account {account.get('email_address')}"
            )

        smtp_server = account.get("smtp_server") or ""
        smtp_port = account.get("smtp_port", 587)
        use_tls = account.get("use_tls", True)
        username = account.get("smtp_user") or account.get("email_address")
        password = account.get("smtp_password")

        # Construct EmailMessage
        msg = EmailMessage()
        msg["Subject"] = message.get("subject", "")
        msg["From"] = account.get("email_address")
        msg["To"] = message.get("recipient")
        msg["Message-ID"] = message.get("message_id") or make_msgid()

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
                if username and password:
                    await smtp.login(username, password)
                await smtp.send_message(msg)

            log.info(
                "email.sent", recipient=message.get("recipient"), subject=message.get("subject")
            )
            await EmailService._log_outgoing(account, message, msg, status="Sent")
        except Exception as e:
            log.error("email.send_failed", error=str(e), recipient=message.get("recipient"))
            await EmailService._log_outgoing(
                account, message, msg, status="Error", error=str(e), dedup=False
            )
            raise

    @staticmethod
    async def _log_outgoing(
        account: dict[str, Any],
        message: dict[str, Any],
        msg: EmailMessage,
        *,
        status: str,
        error: str | None = None,
        dedup: bool = True,
    ) -> None:
        html = bool(message.get("is_html") or message.get("html"))
        content = message.get("content", "")
        plain = message.get("text_content") or message.get("text") or None
        await EmailService.record_message(
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
            message_id=(msg["Message-ID"] if dedup else None),
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
    async def store_bytes(content: bytes, filename: str, mimetype: str | None) -> str | None:
        """Save raw bytes through the storage backend as a private File; return its URL."""
        try:
            # Mail attachments are private; the UI opens them via signed URLs
            # (grunt.storage.signing).
            fdoc = await store(content, filename or "attachment", mimetype)
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
        session: AsyncSession | None = None,
    ) -> str | None:
        """Best-effort: persist one ``EmailMessage`` row (dedup by Message-ID)."""
        try:
            sess = session or grunt.get_session()
        except RuntimeError:
            log.warning("email.record_no_session")
            return None

        mid = (message_id or "").strip() or None
        att_rows = attachments or []
        try:
            async with grunt.system_context(sess):
                if mid and await grunt.db.exists("EmailMessage", {"message_id": mid}):
                    return None
                doc = await grunt.new_doc(
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
        async with grunt.system_context(session):
            configured = await get_setting("default_email_account")
            if configured and await grunt.db.exists("EmailAccount", {"name": configured}):
                return str(configured)
            accounts = await grunt.db.get_all(
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
    ) -> str:
        """Insert a record into EmailQueue for async delivery.

        Sending account: ``SystemSettings.default_email_account`` when set,
        otherwise the first EmailAccount with ``enable_outgoing=True``.
        ``SystemSettings.email_footer`` (if any) is appended to the body.

        ``attachments`` - ``[{"filename", "mimetype", "content": bytes}]``; kept
        base64-encoded on the queue row (never as public File records).
        """
        # Resolve the outgoing account id (best-effort - None if unconfigured)
        email_account_id: str | None = None
        footer: str = ""
        try:
            email_account_id = await EmailService.resolve_outgoing_account_id(session)
            async with grunt.system_context(session):
                raw_footer = (await get_setting("email_footer") or "").strip()
                # Ignore markup-only footers like "<p></p>" that a rich-text
                # editor leaves behind when the field is "empty".
                if re.sub(r"<[^>]+>", "", raw_footer).strip():
                    footer = raw_footer
        except Exception:
            log.exception("suppressed_error")

        is_html = bool(html_body)
        html_content = html_body or ""
        text_content = body
        if footer:
            plain_footer = re.sub(r"<[^>]+>", "", footer).strip()
            text_content = f"{body}\n\n{plain_footer}"
            if is_html:
                html_content = f"{html_body}<br><br>{footer}"

        # ``content`` is what SMTP sends as the primary body; ``text_content`` is
        # the ``text/plain`` alternative (and the fallback for HTML mail).
        content = html_content if is_html else text_content

        record_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        try:
            async with grunt.system_context(session):
                await grunt.db.insert_one(
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
                    },
                )
        except Exception:
            log.warning("email.queue_doctype_missing")
            return ""

        _kick_queue_after_commit(session)
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
