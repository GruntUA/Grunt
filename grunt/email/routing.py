"""Incoming letter -> document (FRAPPE_GAP #13).

:func:`file_inbound` files one letter from a mailbox:

1. A reply - ``In-Reply-To`` / ``References`` names a letter already on a
   document - lands on that document.
2. Otherwise, when the mailbox's ``append_to`` names a DocType with
   ``email_append_to``, a new document of it is created: the sender's address
   into ``sender_field``, the subject into ``subject_field``.
3. Otherwise the letter only goes to the mailbox (``EmailMessage``), as before.

The letter's files become the document's attachments. A letter that created a
document gets the mailbox's auto-reply, unless a robot or a list sent it.
"""

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.db.api import GruntDB
from grunt.email.compose import reply_subject, send_on_document, thread_headers, with_signature
from grunt.email.inbound import sender_address
from grunt.email.service import EmailService
from grunt.i18n import _
from grunt.local import system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session


def _thread_ids(email_data: dict[str, Any]) -> list[str]:
    ids = re.findall(r"<[^>]+>", str(email_data.get("references") or ""))
    if email_data.get("in_reply_to"):
        ids.append(str(email_data["in_reply_to"]))
    return list(dict.fromkeys(ids))


async def thread_document(email_data: dict[str, Any]) -> tuple[str, str] | None:
    """The document the letter answers - the newest known letter of its thread
    that is on a document still there."""
    ids = _thread_ids(email_data)
    if not ids:
        return None
    rows = await _db.get_all(
        "EmailMessage",
        filters={"message_id__in": ids, "ref_doctype__is": "set", "ref_name__is": "set"},
        fields=["ref_doctype", "ref_name"],
        order_by="created_at",
        order="desc",
        limit=len(ids),
    )
    for row in rows:
        doctype, name = str(row.ref_doctype), str(row.ref_name)
        if await doctype_registry.get_meta(doctype) and await _db.exists(doctype, name):
            return doctype, name
    return None


async def create_document(
    session: AsyncSession, doctype: str, email_data: dict[str, Any]
) -> str | None:
    """A new *doctype* document from the letter; None when the DocType doesn't
    take mail or the document can't be created (the letter then stays in the
    mailbox only)."""
    meta = await doctype_registry.get_meta(doctype)
    if meta is None or not meta.email_append_to:
        log.warning("email.append_to_not_enabled", doctype=doctype)
        return None
    data: dict[str, Any] = {}
    if meta.sender_field:
        data[meta.sender_field] = sender_address(email_data.get("sender"))
    if meta.subject_field:
        field = meta.get_field(meta.subject_field)
        limit = getattr(field, "length", None) or 140
        subject = (email_data.get("subject") or "").strip() or _("(no subject)")
        data[meta.subject_field] = subject[:limit]
    try:
        async with session.begin_nested():
            doc = await documents.new_doc(doctype, data)
    except Exception:  # noqa: BLE001 - a required field we can't fill: keep the letter
        log.exception("email.append_to_failed", doctype=doctype)
        return None
    return str(doc.name)


async def _store_attachments(
    email_data: dict[str, Any], ref: tuple[str, str] | None
) -> list[dict[str, Any]]:
    rows = []
    for att in email_data.get("attachments") or []:
        content = att.get("content") or b""
        url = await EmailService.store_bytes(
            content,
            att.get("filename") or "attachment",
            att.get("mimetype"),
            attached_to_doctype=ref[0] if ref else None,
            attached_to_id=ref[1] if ref else None,
        )
        rows.append(
            {
                "file": url,
                "filename": att.get("filename") or "attachment",
                "size": len(content),
                "mimetype": att.get("mimetype") or "",
            }
        )
    return rows


def _format(template: str, context: dict[str, Any]) -> str:
    try:
        return template.format(**context)
    except KeyError, IndexError, ValueError:
        return template


def may_auto_reply(account: dict[str, Any], email_data: dict[str, Any]) -> bool:
    """Not to robots and lists, nor to the mailbox itself (no reply loops)."""
    if not account.get("auto_reply") or email_data.get("auto_generated"):
        return False
    sender = sender_address(email_data.get("sender"))
    own = {str(account.get(k) or "").strip().lower() for k in ("email_address", "reply_to")}
    return bool(sender) and sender not in own


async def auto_reply(
    session: AsyncSession,
    account: dict[str, Any],
    email_data: dict[str, Any],
    doctype: str,
    name: str,
) -> str | None:
    """Answer the letter that created document *doctype*/*name*."""
    context = {
        "name": name,
        "subject": email_data.get("subject") or "",
        "sender": sender_address(email_data.get("sender")),
    }
    text = (account.get("auto_reply_message") or "").strip()
    body = (
        _format(text, context)
        if re.sub(r"<[^>]+>", "", text).strip()
        else "<p>"
        + _("We have received your letter and registered it as %(name)s. We will answer soon.")
        % {"name": name}
        + "</p>"
    )
    in_reply_to, references = thread_headers(
        {
            "message_id": email_data.get("message_id"),
            "message_references": email_data.get("references"),
            "in_reply_to": email_data.get("in_reply_to"),
        }
    )
    return await send_on_document(
        session,
        account=account,
        doctype=doctype,
        name=name,
        to=context["sender"],
        subject=reply_subject(email_data.get("subject")),
        body_html=with_signature(body, account),
        in_reply_to=in_reply_to,
        message_references=references,
        is_auto_reply=True,
    )


async def file_inbound(
    session: AsyncSession, account: dict[str, Any], email_data: dict[str, Any]
) -> dict[str, Any] | None:
    """File one ordinary incoming letter (see the module doc). Returns
    ``{"message", "ref_doctype", "ref_name", "created"}``, or None for a letter
    already filed (same Message-ID)."""
    async with system_context(session):
        mid = (email_data.get("message_id") or "").strip()
        if mid and await _db.exists("EmailMessage", {"message_id": mid}):
            return None

        ref = await thread_document(email_data)
        created = False
        if ref is None and account.get("append_to"):
            name = await create_document(session, str(account["append_to"]), email_data)
            if name:
                ref, created = (str(account["append_to"]), name), True

        message = await EmailService.record_message(
            direction="Incoming",
            status="Received",
            subject=email_data.get("subject", ""),
            sender=email_data.get("sender", ""),
            recipients=email_data.get("recipients", ""),
            cc=email_data.get("cc") or None,
            email_account=account.get("name"),
            body_html=email_data.get("html") or None,
            body_text=email_data.get("text") or None,
            message_date=EmailService.parse_date(email_data.get("date")),
            message_id=mid or None,
            in_reply_to=email_data.get("in_reply_to"),
            message_references=email_data.get("references"),
            ref_doctype=ref[0] if ref else None,
            ref_name=ref[1] if ref else None,
            attachments=await _store_attachments(email_data, ref),
            session=session,
        )

        if created and ref and may_auto_reply(account, email_data):
            try:
                await auto_reply(session, account, email_data, *ref)
            except Exception:  # noqa: BLE001 - the letter is filed; the reply is a courtesy
                log.exception("email.auto_reply_failed", doctype=ref[0], name=ref[1])

    return {
        "message": message,
        "ref_doctype": ref[0] if ref else None,
        "ref_name": ref[1] if ref else None,
        "created": created,
    }
