"""Inbound mail - IMAP fetch, MIME parsing, delivery/read-receipt reports.

Outgoing mail (SMTP, the queue, the ``EmailMessage`` log) lives in
``grunt.email.service``.
"""

import email
import re
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from typing import Any

import aioimaplib
from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import log


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
                emails.append(parse_message(msg))
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


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def parse_message(msg: Message) -> dict[str, Any]:
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
                            "filename": decode_header_value(filename) or "attachment",
                            "content": payload,
                            "mimetype": ctype,
                        }
                    )
                continue
            payload = part.get_payload(decode=True)
            if not payload or not isinstance(payload, bytes):
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", "replace")
            if ctype == "text/plain" and not text_body:
                text_body = text
            elif ctype == "text/html" and not html_body:
                html_body = text
    else:
        payload = msg.get_payload(decode=True)
        text = (
            payload.decode(msg.get_content_charset() or "utf-8", "replace")
            if isinstance(payload, bytes)
            else ""
        )
        if msg.get_content_type() == "text/html":
            html_body = text
        else:
            text_body = text

    return {
        "message_id": (msg["Message-ID"] or "").strip() or None,
        "sender": decode_header_value(msg["From"]),
        "recipients": decode_header_value(msg["To"]),
        "cc": decode_header_value(msg["Cc"]),
        "subject": decode_header_value(msg["Subject"]),
        "date": msg["Date"],
        "text": text_body,
        "html": html_body,
        "attachments": attachments,
        "report": parse_report(msg, text_body),
    }


# Delivery / read-receipt reports (DSN / MDN)


def _find_part(msg: Message, content_type: str) -> Any | None:
    for part in msg.walk():
        if part.get_content_type() == content_type:
            return part
    return None


def _clean_mid(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    m = re.search(r"<[^>]+>", value)
    return m.group(0) if m else (value or None)


def _orig_message_id(msg: Message, text_body: str = "") -> str | None:
    """Dig the original Message-ID out of a bounce/MDN report."""
    rfc822 = _find_part(msg, "message/rfc822")
    if rfc822 is not None:
        payload = rfc822.get_payload()
        inner = payload[0] if isinstance(payload, list) and payload else None
        if inner is not None and inner.get("Message-ID"):
            return _clean_mid(inner["Message-ID"])

    hdrs = _find_part(msg, "text/rfc822-headers")
    if hdrs is not None:
        raw = hdrs.get_payload(decode=True)
        if raw:
            parsed = email.message_from_bytes(raw)
            if parsed.get("Message-ID"):
                return _clean_mid(parsed["Message-ID"])

    # last resort: scan any text for a Message-ID: line
    for blob in (text_body, str(msg)):
        m = re.search(r"(?im)^\s*(?:original-)?message-id\s*:\s*(<[^>]+>)", blob or "")
        if m:
            return m.group(1)
    return None


def parse_report(msg: Message, text_body: str = "") -> dict[str, Any] | None:
    """Classify a message as a delivery-status (DSN) or read-receipt (MDN)
    report and extract the referenced original Message-ID.

    Returns ``None`` for ordinary mail.
    """
    report_type = ""
    if msg.get_content_maintype() == "multipart":
        param = msg.get_param("report-type")
        report_type = param.lower() if isinstance(param, str) else ""

    from_hdr = decode_header_value(msg["From"]).lower()
    is_daemon = "mailer-daemon" in from_hdr or "postmaster" in from_hdr

    dn_part = _find_part(msg, "message/disposition-notification")
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
            "orig_message_id": _clean_mid(fields.get("original-message-id"))
            or _orig_message_id(msg, text_body),
            "read": "displayed" in disposition,
            "status": None,
            "detail": disposition or "MDN",
        }

    ds_part = _find_part(msg, "message/delivery-status")
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
            "failed": "Undelivered",
            "delayed": "Deferred",
            "delivered": "Delivered",
            "relayed": "Delivered",
            "expanded": "Delivered",
        }
        orig = _orig_message_id(msg, text_body)
        status = status_map.get(action) or ("Undelivered" if is_daemon else None)
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


async def apply_report(report: dict[str, Any], session: AsyncSession | None = None) -> None:
    """Update the referenced outgoing ``EmailMessage`` from a DSN/MDN report."""
    try:
        sess = session or grunt.get_session()
    except RuntimeError:
        return

    orig = (report.get("orig_message_id") or "").strip()
    if not orig:
        log.warning("email.report_no_orig", kind=report.get("kind"))
        return

    async with grunt.system_context(sess):
        row = await grunt.db.get_value(
            "EmailMessage",
            {"message_id": orig, "direction": "Outgoing"},
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
                if cur in ("Sent", "Deferred"):
                    updates["status"] = "Delivered"
                    updates["delivered_at"] = now
        else:  # dsn
            new_status = report.get("status")
            if new_status == "Undelivered" or new_status == "Deferred" and cur == "Sent":
                updates["status"] = new_status
            elif new_status == "Delivered" and cur in ("Sent", "Deferred"):
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
