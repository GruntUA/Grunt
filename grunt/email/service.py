from __future__ import annotations

import asyncio
import base64
import email
import json
import re
import uuid
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import make_msgid, parsedate_to_datetime
from typing import TYPE_CHECKING, Any

import aioimaplib
import aiosmtplib

from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
    from sqlalchemy import event

    sync_session = session.sync_session
    if getattr(sync_session, "_grunt_email_kick_armed", False):
        return
    sync_session._grunt_email_kick_armed = True

    def _on_commit(_s: Any) -> None:
        sync_session._grunt_email_kick_armed = False
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

    - ``465`` → implicit TLS from the first byte (SMTPS).
    - ``587`` / ``25`` / other → connect in plaintext, then upgrade via
      STARTTLS: forced when ``use_tls`` is set, best-effort otherwise.

    Passing ``use_tls=True`` on port 587 (as a naive reading of the account's
    "use TLS" checkbox suggests) makes the client start a TLS handshake against
    a plaintext SMTP banner — Gmail then fails with
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
    """Service for asynchronous SMTP and IMAP operations."""

    @staticmethod
    async def send_now(account: dict[str, Any], message: dict[str, Any]) -> None:
        """Send an email immediately using the provided account settings."""
        if not account.get("enable_outgoing"):
            raise ValueError(
                f"Outgoing email is disabled for account {account.get('email_address')}"
            )

        smtp_server = account.get("smtp_server")
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
            # by some clients and only with the user's consent — best-effort.
            receipt_addr = account.get("email_address")
            msg["Disposition-Notification-To"] = receipt_addr
            msg["Return-Receipt-To"] = receipt_addr

        content = message.get("content", "")
        if message.get("is_html") or message.get("html"):
            plain = (
                message.get("text_content")
                or message.get("text")
                or "Це повідомлення у форматі HTML."
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
            maintype, _, subtype = mimetype.partition("/")
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
            await EmailService._log_outgoing(account, message, msg, status="Надіслано")
        except Exception as e:
            log.error("email.send_failed", error=str(e), recipient=message.get("recipient"))
            await EmailService._log_outgoing(
                account, message, msg, status="Помилка", error=str(e), dedup=False
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
            direction="Вихідний",
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
    async def pull_emails(account: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch unread emails from the IMAP server and mark them ``\\Seen``.

        Each returned dict: ``message_id, sender, recipients, cc, subject, date,
        text, html, attachments`` where ``attachments`` is a list of
        ``{filename, content: bytes, mimetype}``.
        """
        if not account.get("enable_incoming"):
            return []

        imap_server: str | None = account.get("imap_server")
        imap_port: int = account.get("imap_port", 993)
        use_ssl: bool = account.get("use_ssl", True)
        username: str | None = account.get("email_address")
        password: str | None = account.get("smtp_password")

        if not imap_server or not username or not password:
            return []

        emails: list[dict[str, Any]] = []

        try:
            imap = (
                aioimaplib.IMAP4_SSL(imap_server, imap_port)
                if use_ssl
                else aioimaplib.IMAP4(imap_server, imap_port)
            )
            await imap.wait_hello_from_server()
            await imap.login(username, password)
            await imap.select("INBOX")

            status, messages = await imap.search("UNSEEN")
            if status == "OK" and messages and messages[0]:
                for num in messages[0].split():
                    st, data = await imap.fetch(num, "(RFC822)")
                    if st != "OK" or not data or not isinstance(data[1], (bytes, bytearray)):
                        continue
                    msg = email.message_from_bytes(data[1])
                    emails.append(EmailService._parse_message(msg))
                    num_str = num.decode() if isinstance(num, bytes) else str(num)
                    try:
                        await imap.store(num_str, "+FLAGS", "\\Seen")
                    except Exception:
                        log.warning("email.imap_mark_seen_failed", num=num_str)

            await imap.logout()
            log.info("email.pulled", count=len(emails), account=username)

        except Exception as e:
            log.error("email.pull_failed", error=str(e), account=username)

        return emails

    @staticmethod
    def _decode_header(value: str | None) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return str(value)

    @staticmethod
    def _parse_message(msg: email.message.Message) -> dict[str, Any]:
        text_body, html_body = "", ""
        attachments: list[dict[str, Any]] = []

        if msg.is_multipart():
            for part in msg.walk():
                if part.is_multipart():
                    continue
                ctype = part.get_content_type()
                disposition = str(part.get("Content-Disposition") or "").lower()
                filename = part.get_filename()
                if "attachment" in disposition or filename:
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append(
                            {
                                "filename": EmailService._decode_header(filename) or "attachment",
                                "content": payload,
                                "mimetype": ctype,
                            }
                        )
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                text = payload.decode(part.get_content_charset() or "utf-8", "replace")
                if ctype == "text/plain" and not text_body:
                    text_body = text
                elif ctype == "text/html" and not html_body:
                    html_body = text
        else:
            payload = msg.get_payload(decode=True)
            text = (
                payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""
            )
            if msg.get_content_type() == "text/html":
                html_body = text
            else:
                text_body = text

        return {
            "message_id": (msg["Message-ID"] or "").strip() or None,
            "sender": EmailService._decode_header(msg["From"]),
            "recipients": EmailService._decode_header(msg["To"]),
            "cc": EmailService._decode_header(msg["Cc"]),
            "subject": EmailService._decode_header(msg["Subject"]),
            "date": msg["Date"],
            "text": text_body,
            "html": html_body,
            "attachments": attachments,
            "report": EmailService._parse_report(msg, text_body),
        }

    # ── Delivery / read-receipt reports (DSN / MDN) ──────────────────────────

    @staticmethod
    def _find_part(msg: email.message.Message, content_type: str) -> Any | None:
        for part in msg.walk():
            if part.get_content_type() == content_type:
                return part
        return None

    @staticmethod
    def _clean_mid(value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        m = re.search(r"<[^>]+>", value)
        return m.group(0) if m else (value or None)

    @staticmethod
    def _orig_message_id(msg: email.message.Message, text_body: str = "") -> str | None:
        """Dig the original Message-ID out of a bounce/MDN report."""
        rfc822 = EmailService._find_part(msg, "message/rfc822")
        if rfc822 is not None:
            payload = rfc822.get_payload()
            inner = payload[0] if isinstance(payload, list) and payload else None
            if inner is not None and inner.get("Message-ID"):
                return EmailService._clean_mid(inner["Message-ID"])

        hdrs = EmailService._find_part(msg, "text/rfc822-headers")
        if hdrs is not None:
            raw = hdrs.get_payload(decode=True)
            if raw:
                parsed = email.message_from_bytes(raw)
                if parsed.get("Message-ID"):
                    return EmailService._clean_mid(parsed["Message-ID"])

        # last resort: scan any text for a Message-ID: line
        for blob in (text_body, str(msg)):
            m = re.search(r"(?im)^\s*(?:original-)?message-id\s*:\s*(<[^>]+>)", blob or "")
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _parse_report(msg: email.message.Message, text_body: str = "") -> dict[str, Any] | None:
        """Classify a message as a delivery-status (DSN) or read-receipt (MDN)
        report and extract the referenced original Message-ID.

        Returns ``None`` for ordinary mail.
        """
        report_type = ""
        if msg.get_content_maintype() == "multipart":
            report_type = (msg.get_param("report-type") or "").lower()

        from_hdr = EmailService._decode_header(msg["From"]).lower()
        is_daemon = "mailer-daemon" in from_hdr or "postmaster" in from_hdr

        dn_part = EmailService._find_part(msg, "message/disposition-notification")
        if report_type == "disposition-notification" or dn_part is not None:
            fields: dict[str, str] = {}
            if dn_part is not None:
                payload = dn_part.get_payload()
                inner = (
                    payload[0]
                    if isinstance(payload, list) and payload and hasattr(payload[0], "items")
                    else None
                )
                if inner is not None:
                    for k, v in inner.items():
                        fields[k.lower()] = v
                else:
                    raw = dn_part.get_payload(decode=True)
                    if raw:
                        for k, v in email.message_from_bytes(raw).items():
                            fields[k.lower()] = v
            disposition = (fields.get("disposition") or "").lower()
            return {
                "kind": "mdn",
                "orig_message_id": EmailService._clean_mid(fields.get("original-message-id"))
                or EmailService._orig_message_id(msg, text_body),
                "read": "displayed" in disposition,
                "status": None,
                "detail": disposition or "MDN",
            }

        ds_part = EmailService._find_part(msg, "message/delivery-status")
        if report_type == "delivery-status" or ds_part is not None or is_daemon:
            action, diag, dstat = "", "", ""
            if ds_part is not None:
                blocks = ds_part.get_payload()
                if not isinstance(blocks, list):
                    blocks = [ds_part]
                for block in blocks:
                    if not hasattr(block, "items"):
                        continue
                    bf = {k.lower(): v for k, v in block.items()}
                    a = (bf.get("action") or "").lower()
                    if not a:
                        continue
                    action, diag, dstat = (
                        a,
                        bf.get("diagnostic-code") or diag,
                        bf.get("status") or dstat,
                    )
                    if a == "failed":
                        break
            status_map = {
                "failed": "Не доставлено",
                "delayed": "Відкладено",
                "delivered": "Доставлено",
                "relayed": "Доставлено",
                "expanded": "Доставлено",
            }
            orig = EmailService._orig_message_id(msg, text_body)
            status = status_map.get(action) or ("Не доставлено" if is_daemon else None)
            if status is None:
                return None
            # A message merely *from* postmaster/mailer-daemon with no
            # delivery-status part and no traceable original is treated as
            # ordinary mail, not a bounce.
            if ds_part is None and report_type != "delivery-status" and not orig:
                return None
            detail = " · ".join(p for p in (dstat, diag) if p) or action or "bounce"
            if not detail.strip() and text_body:
                detail = text_body.strip()[:400]
            return {
                "kind": "dsn",
                "orig_message_id": orig,
                "read": False,
                "status": status,
                "detail": detail[:2000],
            }

        return None

    @staticmethod
    async def apply_report(report: dict[str, Any], session: AsyncSession | None = None) -> None:
        """Update the referenced outgoing ``EmailMessage`` from a DSN/MDN report."""
        from grunt.app import grunt

        try:
            from grunt.context import require_session

            sess = session or require_session()
        except Exception:
            return

        orig = (report.get("orig_message_id") or "").strip()
        if not orig:
            log.warning("email.report_no_orig", kind=report.get("kind"))
            return

        async with grunt.system_context(sess):
            row = await grunt.db.get_value(
                "EmailMessage",
                {"message_id": orig, "direction": "Вихідний"},
                ["name", "status"],
                as_dict=True,
            )
            if not row:
                log.info("email.report_unmatched", orig=orig, kind=report.get("kind"))
                return

            cur = row.get("status")
            now = datetime.now(UTC)
            updates: dict[str, Any] = {}

            if report["kind"] == "mdn":
                if report.get("read"):
                    updates["read_at"] = now
                    updates["delivery_detail"] = report.get("detail")
                    if cur in ("Надіслано", "Відкладено"):
                        updates["status"] = "Доставлено"
                        updates["delivered_at"] = now
            else:  # dsn
                new_status = report.get("status")
                if (
                    new_status == "Не доставлено"
                    or new_status == "Відкладено"
                    and cur == "Надіслано"
                ):
                    updates["status"] = new_status
                elif new_status == "Доставлено" and cur in ("Надіслано", "Відкладено"):
                    updates["status"] = new_status
                    updates["delivered_at"] = now
                if report.get("detail"):
                    updates["delivery_detail"] = report["detail"]

            if updates:
                await grunt.save_doc("EmailMessage", row["name"], updates)
                log.info(
                    "email.report_applied",
                    name=row["name"],
                    kind=report.get("kind"),
                    updates=list(updates),
                )

    @staticmethod
    async def store_bytes(content: bytes, filename: str, mimetype: str | None) -> str | None:
        """Save raw bytes through the storage backend as a private File; return its URL."""
        from grunt.app import grunt
        from grunt.storage import get_storage_backend

        try:
            path = await get_storage_backend().save(
                content=content,
                filename=filename or "attachment",
                content_type=mimetype or "application/octet-stream",
            )
            fdoc = await grunt.new_doc(
                "File",
                {
                    "file_name": filename or "attachment",
                    "path": path,
                    "content_type": mimetype or "application/octet-stream",
                    "file_size": len(content),
                    # Mail attachments are private; the UI opens them via
                    # signed URLs (grunt.storage.signing).
                    "is_public": False,
                    "file_url": "",
                },
            )
            fid = fdoc.get("name")
            url = f"/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id={fid}"
            await grunt.db.set_value("File", fid, {"file_url": url})
            return url
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
        from grunt.app import grunt

        try:
            from grunt.context import require_session

            sess = session or require_session()
        except Exception:
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
                            bool(is_read) if is_read is not None else (direction == "Вихідний")
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
        from grunt.app import grunt
        from grunt.site.settings import get_setting

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

        ``attachments`` — ``[{"filename", "mimetype", "content": bytes}]``; kept
        base64-encoded on the queue row (never as public File records).
        """
        from grunt.app import grunt
        from grunt.site.settings import get_setting

        # Resolve the outgoing account id (best-effort — None if unconfigured)
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
                        "docstatus": 0,
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
    """``content: bytes`` → ``content_b64`` so attachments fit a JSON column."""
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
    """Inverse of :func:`encode_attachments` — what :meth:`EmailService.send_now` takes."""
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
