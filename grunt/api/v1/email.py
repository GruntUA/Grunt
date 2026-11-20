"""Email management whitelisted methods; letters on a document.

RPC: grunt.api.v1.email.compose_context
RPC: grunt.api.v1.email.render_email_template
RPC: grunt.api.v1.email.send_email
"""

import html as html_lib
import re
from typing import Any

import aiosmtplib

from grunt.api.context import whitelist
from grunt.api.results import Outcome
from grunt.db.api import GruntDB
from grunt.email.compose import account_for, reply_subject, send_on_document, thread_headers
from grunt.email.service import (
    SMTP_PASSWORD_MASK,
    EmailService,
    smtp_connect_kwargs,
    split_addresses,
)
from grunt.email.templates import EmailTemplateError
from grunt.email.templates import render as render_template
from grunt.errors import forbidden, not_found, unprocessable
from grunt.i18n import _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.notification.rules import MAX_ATTACH_BYTES
from grunt.permissions.guards import doc_guard
from grunt.permissions.rbac import permission_checker
from grunt.utils.sanitize import sanitize_html
from grunt.validators.email import EmailValidator
lazy from grunt.document.api import documents
lazy from grunt.print.pdf import html_to_pdf
lazy from grunt.print.renderer import render_print_html
lazy from grunt.storage.files import read as read_file

EMAIL_RE = re.compile(EmailValidator.pattern)

_db = GruntDB()  # stateless: reads through the context's session


def _mask_password(account: dict[str, Any]) -> dict[str, Any]:
    if account.get("smtp_password"):
        account["smtp_password"] = SMTP_PASSWORD_MASK
    return account


@whitelist(perm="grunt.manage_email")
async def test_smtp_connection(
    smtp_server: str,
    smtp_port: int = 587,
    use_tls: bool = True,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    account_id: str | None = None,
) -> Outcome:
    """Attempt SMTP connect+login without sending a message.

    When ``account_id`` is given and no fresh password was typed, the stored
    password of that account is used (reads mask it, so the form can't send it
    back).
    """
    if account_id and (not smtp_password or smtp_password == SMTP_PASSWORD_MASK):
        smtp_password = await _db.get_value("EmailAccount", account_id, "smtp_password")
    try:
        async with aiosmtplib.SMTP(
            timeout=10,
            **smtp_connect_kwargs(smtp_server, smtp_port, bool(use_tls)),
        ) as smtp:
            if smtp_user and smtp_password:
                await smtp.login(smtp_user, smtp_password)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@whitelist(perm="grunt.manage_email")
async def send_test_email(account_id: str, recipient: str) -> Outcome:
    """Send a short test message through a saved EmailAccount.

    Uses the stored SMTP settings (the caller is System Manager, so the
    ``after_read`` mask does not apply and the real password is available).
    """
    recipient = (recipient or "").strip()
    if not recipient:
        return {"success": False, "error": _("No recipient address specified.")}

    account = dict(await documents.get_doc("EmailAccount", account_id))
    if not account.get("enable_outgoing"):
        return {"success": False, "error": _("Outgoing email is disabled for this account.")}

    # Reads mask the password - pull the real one straight from the column.
    account["smtp_password"] = await _db.get_value("EmailAccount", account_id, "smtp_password")
    if not account["smtp_password"]:
        return {
            "success": False,
            "error": _("The SMTP password is not saved. Save the account with a password."),
        }

    try:
        await EmailService.send_now(
            account,
            {
                "subject": _("Grunt test email"),
                "recipient": recipient,
                "content": (
                    _("This is a test email sent from Grunt.")
                    + "\n\n"
                    + _("If you received it, sending email through this account works.")
                ),
            },
        )
        return {"success": True}
    except Exception as e:
        log.warning("email.test_send_failed", account=account_id, error=str(e))
        return {"success": False, "error": str(e)}


@whitelist(perm="grunt.manage_email")
async def list_accounts() -> list[dict[str, Any]]:
    result = await documents.get_list("EmailAccount", limit=1000, order_by="created_at")
    return [_mask_password(dict(acc)) for acc in result]


@whitelist(perm="grunt.manage_email")
async def get_account(account_id: str) -> dict[str, Any]:
    data = await documents.get_doc("EmailAccount", account_id)
    return _mask_password(dict(data))


@whitelist(perm="grunt.manage_email")
async def list_queue(
    status: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    page = int(page)
    per_page = int(per_page)
    filters = {"status": status} if status else None
    records = await documents.get_list(
        "EmailQueue",
        limit=per_page,
        page=page,
        order_by="created_at",
        order="desc",
        filters=filters,
    )
    total = await documents.count("EmailQueue", filters=filters)
    return {"items": records, "total": total, "page": page, "per_page": per_page}


@whitelist(perm="grunt.manage_email")
async def retry_item(queue_id: str) -> bool:
    await _db.set_value("EmailQueue", queue_id, {"status": "Pending", "error_message": None})
    return True


# Letters on a document (its timeline: "Write an email" / "Reply")


async def _thread_anchor(doctype: str, doc_id: str, reply_to: str | None) -> dict[str, Any] | None:
    """The letter a new one answers: *reply_to* when it is on this document,
    else the document's latest letter (keeps the correspondence one thread)."""
    fields = [
        "name",
        "direction",
        "subject",
        "sender",
        "recipients",
        "cc",
        "email_account",
        "message_id",
        "in_reply_to",
        "message_references",
    ]
    filters: dict[str, Any] = {"ref_doctype": doctype, "ref_name": doc_id}
    if reply_to:
        filters["name"] = reply_to
    async with system_context(require_session()):
        rows = await _db.get_all(
            "EmailMessage",
            filters=filters,
            fields=fields,
            order_by="created_at",
            order="desc",
            limit=1,
        )
    if reply_to and not rows:
        raise not_found(_("The letter is not on this document"))
    return dict(rows[0]) if rows else None


async def _outgoing_accounts() -> list[dict[str, Any]]:
    async with system_context(require_session()):
        rows = await _db.get_all(
            "EmailAccount",
            filters={"enable_outgoing": True},
            fields=["name", "email_address", "signature"],
            order_by="email_address",
            order="asc",
            limit=None,
        )
    return [dict(r) for r in rows]


@whitelist()
async def compose_context(doctype: str, doc_id: str, reply_to: str | None = None) -> dict[str, Any]:
    """What the "Write an email" dialog starts with: the mailboxes, the one to
    send from, the addressee and subject (a reply - to the answered letter's
    correspondent), the signature, the document's files and the templates."""
    doc = await doc_guard(doctype, doc_id, "write")
    meta = await doctype_registry.get_meta(doctype)
    accounts = await _outgoing_accounts()
    anchor = await _thread_anchor(doctype, doc_id, reply_to)
    async with system_context(require_session()):
        default = (anchor or {}).get("email_account") or await account_for(doctype, doc_id)
    names = {a["name"] for a in accounts}
    if default not in names:
        default = accounts[0]["name"] if accounts else None

    to, cc, subject = "", "", ""
    if anchor and reply_to:
        if anchor["direction"] == "Incoming":
            to = anchor.get("sender") or ""
        else:
            to, cc = anchor.get("recipients") or "", anchor.get("cc") or ""
        subject = reply_subject(anchor.get("subject"))
    else:
        if meta and meta.sender_field and doc.get(meta.sender_field):
            to = str(doc[meta.sender_field])
        elif anchor and anchor["direction"] == "Incoming":
            to = anchor.get("sender") or ""
        title_field = (meta.subject_field or meta.title_field) if meta else None
        subject = str(doc.get(title_field or "name") or doc_id)
        if anchor:
            subject = reply_subject(anchor.get("subject") or subject)

    async with system_context(require_session()):
        files = await _db.get_all(
            "File",
            filters={"attached_to_doctype": doctype, "attached_to_id": doc_id},
            fields=["name", "file_name", "file_size"],
            order_by="created_at",
            order="asc",
            limit=50,
        )
        templates = await _db.get_all(
            "EmailTemplate",
            filters={"is_active": True},
            fields=["name", "label"],
            order_by="label",
            order="asc",
            limit=200,
        )
    return {
        "accounts": [{"name": a["name"], "email_address": a["email_address"]} for a in accounts],
        "signatures": {a["name"]: a.get("signature") or "" for a in accounts},
        "account": default,
        "to": to,
        "cc": cc,
        "subject": subject,
        "files": [dict(f) for f in files],
        "templates": [dict(t) for t in templates],
        "can_print": await permission_checker.check(meta, "print", doc) if meta else False,
    }


@whitelist()
async def render_email_template(doctype: str, doc_id: str, template: str) -> dict[str, Any]:
    """An EmailTemplate filled with the document's values (``{field}``)."""
    await doc_guard(doctype, doc_id, "write")
    doc = await documents.get_doc(doctype, doc_id)
    context = {k: ("" if v is None else v) for k, v in dict(doc).items() if not isinstance(v, list)}
    try:
        subject, body_text, body_html = await render_template(template, context)
    except EmailTemplateError as e:
        raise not_found(str(e)) from e
    body = body_html or "".join(
        f"<p>{html_lib.escape(line)}</p>" for line in body_text.splitlines() if line.strip()
    )
    return {"subject": subject, "body": body}


@whitelist()
async def send_email(
    doctype: str,
    doc_id: str,
    to: str,
    subject: str,
    content: str,
    cc: str | None = None,
    bcc: str | None = None,
    email_account: str | None = None,
    reply_to: str | None = None,
    attach_print: bool = False,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Send a letter from the document (on its timeline at once, ``Queued``).

    Needs write access to the document (and print access for its PDF). The
    files must be the document's own, up to 10 MB in all.
    """
    doc = await doc_guard(doctype, doc_id, "write")
    meta = await doctype_registry.get_meta(doctype)
    if not split_addresses(to):
        raise unprocessable(_("Whom to send it to?"))
    for value in (to, cc, bcc):
        for addr in split_addresses(value):
            if not EMAIL_RE.match(addr):
                raise unprocessable(_("Invalid address: %(address)s") % {"address": addr})

    session = require_session()
    accounts = {a["name"]: a for a in await _outgoing_accounts()}
    async with system_context(session):
        chosen = email_account or await account_for(doctype, doc_id)
    if not chosen or chosen not in accounts:
        raise unprocessable(_("No mailbox to send from - set up an email account"))
    async with system_context(session):
        account = dict(await documents.get_doc("EmailAccount", chosen))

    attachments: list[dict[str, Any]] = []
    total = 0
    if attach_print:
        if not meta or not await permission_checker.check(meta, "print", doc):
            raise forbidden(_("Not permitted to print this document"))
        full = await documents.get_doc(doctype, doc_id)
        async with system_context(session):
            html = await render_print_html(doctype, dict(full))
        pdf = await html_to_pdf(html)
        total += len(pdf)
        attachments.append(
            {"filename": f"{doc_id}.pdf", "mimetype": "application/pdf", "content": pdf}
        )
    if files:
        async with system_context(session):
            rows = await _db.get_all(
                "File",
                filters={
                    "name__in": list(files),
                    "attached_to_doctype": doctype,
                    "attached_to_id": doc_id,
                },
                fields=["name", "file_name", "content_type", "file_size"],
                limit=len(files),
            )
            if len(rows) != len(set(files)):
                raise unprocessable(_("Only the document's own files can be attached"))
            for row in rows:
                data = await read_file(row["name"])
                total += len(data)
                attachments.append(
                    {
                        "filename": row.get("file_name") or row["name"],
                        "mimetype": row.get("content_type") or "application/octet-stream",
                        "content": data,
                    }
                )
    if total > MAX_ATTACH_BYTES:
        raise unprocessable(_("The attachments are over 10 MB"))

    anchor = await _thread_anchor(doctype, doc_id, reply_to)
    in_reply_to, references = thread_headers(anchor) if anchor else (None, None)
    message = await send_on_document(
        session,
        account=account,
        doctype=doctype,
        name=doc_id,
        to=to,
        cc=cc or None,
        bcc=bcc or None,
        subject=subject.strip() or _("(no subject)"),
        body_html=sanitize_html(content or ""),
        attachments=attachments,
        in_reply_to=in_reply_to,
        message_references=references,
    )
    return {"message": message}
