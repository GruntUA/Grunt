"""Letters written on a document - from its timeline or as an auto-reply.

Such a letter is on the document's timeline at once (``EmailMessage`` with
status ``Queued`` and a Message-ID fixed in advance); the queue worker sends it
and moves the same row on to ``Sent`` / ``Error``
(``EmailService.record_message``). A reply to it comes back with that
Message-ID in ``In-Reply-To`` / ``References`` and lands on the same document
(``grunt.email.routing``).
"""

import html as html_lib
import re
from email.utils import make_msgid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.email.service import EmailService, email_service
from grunt.local import require_session, system_context

_db = GruntDB()  # stateless: reads through the context's session

# References kept on a reply: the thread's first letter and the latest ones.
MAX_REFERENCES = 20


def html_to_text(value: str | None) -> str:
    """Plain text of an HTML body - the ``text/plain`` part of the letter."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", value or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def reply_subject(subject: str | None) -> str:
    subject = (subject or "").strip()
    return subject if re.match(r"(?i)^(re|ha|відп)\s*:", subject) else f"Re: {subject}"


def thread_headers(answered: dict[str, Any]) -> tuple[str | None, str | None]:
    """``(In-Reply-To, References)`` for a reply to the ``EmailMessage`` *answered*."""
    mid = (answered.get("message_id") or "").strip() or None
    chain = re.findall(r"<[^>]+>", str(answered.get("message_references") or ""))
    if not chain and answered.get("in_reply_to"):
        chain = [str(answered["in_reply_to"])]
    if mid:
        chain.append(mid)
    if len(chain) > MAX_REFERENCES:
        chain = chain[:1] + chain[-(MAX_REFERENCES - 1) :]
    return mid, " ".join(chain) or None


def with_signature(body_html: str, account: dict[str, Any]) -> str:
    signature = (account.get("signature") or "").strip()
    if not signature or not re.sub(r"<[^>]+>", "", signature).strip():
        return body_html
    return f"{body_html}<br>{signature}"


def _msgid(account: dict[str, Any]) -> str:
    domain = str(account.get("email_address") or "").rpartition("@")[2] or None
    return make_msgid(domain=domain)


async def account_for(doctype: str, name: str) -> str | None:
    """The mailbox a letter on the document goes from by default: the one its
    correspondence came through, else the one creating such documents, else the
    site's default outgoing mailbox."""
    last = await _db.get_all(
        "EmailMessage",
        filters={"ref_doctype": doctype, "ref_name": name, "email_account__is": "set"},
        fields=["email_account"],
        order_by="created_at",
        order="desc",
        limit=1,
    )
    if last:
        return str(last[0]["email_account"])
    own = await _db.get_all(
        "EmailAccount",
        filters={"append_to": doctype, "enable_outgoing": True},
        fields=["name"],
        limit=1,
    )
    if own:
        return str(own[0]["name"])
    return await EmailService.resolve_outgoing_account_id(require_session())


async def send_on_document(
    session: AsyncSession,
    *,
    account: dict[str, Any],
    doctype: str,
    name: str,
    to: str,
    subject: str,
    body_html: str,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    in_reply_to: str | None = None,
    message_references: str | None = None,
    is_auto_reply: bool = False,
) -> str | None:
    """Queue a letter from *account* about document *doctype*/*name* and put it
    on the document's timeline. Returns the ``EmailMessage`` name."""
    message_id = _msgid(account)
    files = attachments or []
    async with system_context(session):
        message = await EmailService.record_message(
            direction="Outgoing",
            status="Queued",
            subject=subject,
            sender=account.get("email_address") or "",
            recipients=to,
            cc=cc,
            email_account=account.get("name"),
            body_html=body_html,
            body_text=html_to_text(body_html),
            message_id=message_id,
            ref_doctype=doctype,
            ref_name=name,
            in_reply_to=in_reply_to,
            message_references=message_references,
            is_auto_reply=is_auto_reply,
            attachments=[
                {
                    "filename": f.get("filename"),
                    "size": len(f.get("content") or b""),
                    "mimetype": f.get("mimetype"),
                }
                for f in files
            ],
            session=session,
        )
        await email_service.queue_email(
            session,
            to,
            subject,
            html_to_text(body_html),
            html_body=body_html,
            attachments=files or None,
            email_account=account.get("name"),
            cc=cc,
            bcc=bcc,
            message_id=message_id,
            in_reply_to=in_reply_to,
            message_references=message_references,
            ref_doctype=doctype,
            ref_name=name,
        )
    return message
