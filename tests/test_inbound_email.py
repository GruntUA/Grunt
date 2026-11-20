"""Incoming mail -> document, letters from a document, mailbox extras
(FRAPPE_GAP #13): threading, append_to, auto-reply, unanswered letters, UID
reading, Cc/Bcc/Reply-To."""

import email
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi import HTTPException

from grunt.api.v1 import email as email_api
from grunt.api.v1.document import history as history_api
from grunt.email import inbound
from grunt.email.inbound import parse_message, pull_emails
from grunt.email.routing import file_inbound
from grunt.email.service import EmailService, envelope_recipients
from grunt.email.tasks import process_unreplied
from grunt.errors import ApplicationError
from tests.support import make_user

ERRORS = (ApplicationError, HTTPException)

CASE = {
    "name": "MailCase",
    "label": "Mail Case",
    "module": "core",
    "email_append_to": True,
    "sender_field": "raised_by",
    "subject_field": "title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "raised_by", "label": "Raised by", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete", "print"]},
        {"role": "Case Agent", "actions": ["read", "write"]},
        {"role": "Case Viewer", "actions": ["read"]},
    ],
}
PLAIN = {
    "name": "MailPlain",
    "label": "Mail Plain",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [{"role": "System Manager", "actions": ["read", "write", "create"]}],
}

BOX = "support@grunt.example.com"
CITIZEN = "citizen@example.org"
AGENT = "agent@grunt.example.com"
DUTY = "duty@grunt.example.com"


@pytest.fixture
async def mailbox(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**CASE, "__is_new": True})
    await save_doctype(doctype_data={**PLAIN, "__is_new": True})
    for role in ("Case Agent", "Case Viewer"):
        await ctx.new_doc("Role", {"role_name": role})
    for addr, first in ((AGENT, "Агент"), (DUTY, "Черговий")):
        await ctx.new_doc("User", {"email": addr, "first_name": first, "last_name": "Т"})
    group = await ctx.new_doc("UserGroup", {"group_name": "Duty", "users": [{"user": DUTY}]})
    account = await ctx.new_doc(
        "EmailAccount",
        {
            "email_address": BOX,
            "enable_outgoing": True,
            "append_to": "MailCase",
            "auto_reply": True,
            "auto_reply_message": "<p>Заявка {name}: {subject}</p>",
            "signature": "<p>-- Служба підтримки</p>",
            "notify_if_unreplied": True,
            "unreplied_minutes": 30,
            "unreplied_group": group["name"],
        },
    )
    await ctx.db._session().commit()
    return dict(await ctx.get_doc("EmailAccount", account["name"]))


def _letter(
    subject="Не працює ліхтар",
    sender=f"Громадянин <{CITIZEN}>",
    mid="<m1@example.org>",
    in_reply_to=None,
    references=None,
    extra=None,
    attach=False,
):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = BOX
    msg["Subject"] = subject
    msg["Message-ID"] = mid
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    for k, v in (extra or {}).items():
        msg[k] = v
    msg.set_content("Біля будинку 5 не світить ліхтар.")
    if attach:
        msg.add_attachment(
            b"%PDF-1.4 x", maintype="application", subtype="pdf", filename="фото.pdf"
        )
    return parse_message(email.message_from_bytes(msg.as_bytes()))


async def _queue(ctx) -> list[dict]:
    return await ctx.db.get_all(
        "EmailQueue",
        fields=[
            "recipient",
            "subject",
            "content",
            "cc",
            "bcc",
            "message_id",
            "in_reply_to",
            "message_references",
            "ref_doctype",
            "ref_name",
            "email_account",
        ],
        order_by="created_at",
        order="asc",
        limit=None,
    )


async def _messages(ctx, **filters) -> list[dict]:
    return await ctx.db.get_all(
        "EmailMessage",
        filters=filters or None,
        fields=[
            "name",
            "direction",
            "status",
            "ref_doctype",
            "ref_name",
            "message_id",
            "in_reply_to",
            "is_auto_reply",
            "unreplied_checked",
        ],
        order_by="created_at",
        order="asc",
        limit=None,
    )


def test_parse_threading_and_robots():
    data = _letter(
        in_reply_to="<a@x>", references="<root@x> <a@x>", extra={"Auto-Submitted": "auto-replied"}
    )
    assert data["in_reply_to"] == "<a@x>"
    assert data["references"] == "<root@x> <a@x>"
    assert data["auto_generated"] is True
    assert _letter()["auto_generated"] is False
    assert _letter(sender="no-reply@shop.example")["auto_generated"] is True
    assert _letter(extra={"Precedence": "bulk"})["auto_generated"] is True
    assert _letter(extra={"List-Id": "<news.example>"})["auto_generated"] is True


@pytest.mark.asyncio
async def test_new_letter_creates_document_with_files_and_auto_reply(ctx, mailbox):
    filed = await file_inbound(ctx.db._session(), mailbox, _letter(attach=True))
    assert filed and filed["created"] and filed["ref_doctype"] == "MailCase"
    case = await ctx.get_doc("MailCase", filed["ref_name"])
    assert (case["raised_by"], case["title"]) == (CITIZEN, "Не працює ліхтар")

    files = await ctx.db.get_all(
        "File",
        filters={"attached_to_doctype": "MailCase", "attached_to_id": case["name"]},
        fields=["file_name"],
    )
    assert [f["file_name"] for f in files] == ["фото.pdf"]
    timeline = await history_api.get_timeline(doctype="MailCase", doc_id=case["name"])
    [letter] = [i for i in timeline if i["type"] == "email" and i["direction"] == "Incoming"]
    assert [a["filename"] for a in letter["attachments"]] == ["фото.pdf"]

    incoming, reply = await _messages(ctx)
    assert (incoming["direction"], incoming["ref_name"]) == ("Incoming", case["name"])
    assert (reply["direction"], reply["status"], reply["is_auto_reply"]) == (
        "Outgoing",
        "Queued",
        True,
    )
    [queued] = await _queue(ctx)
    assert queued["recipient"] == CITIZEN
    assert queued["subject"] == "Re: Не працює ліхтар"
    assert f"Заявка {case['name']}: Не працює ліхтар" in queued["content"]
    assert "Служба підтримки" in queued["content"]
    assert queued["in_reply_to"] == "<m1@example.org>"
    assert queued["message_id"] == reply["message_id"]
    assert (queued["ref_doctype"], queued["ref_name"]) == ("MailCase", case["name"])

    # The same letter again (the next run re-read it) - filed once.
    assert await file_inbound(ctx.db._session(), mailbox, _letter(attach=True)) is None
    assert await ctx.db.count("MailCase") == 1


@pytest.mark.asyncio
async def test_reply_lands_on_its_document_and_robots_get_no_auto_reply(ctx, mailbox):
    first = await file_inbound(
        ctx.db._session(), mailbox, _letter(extra={"Auto-Submitted": "auto-generated"})
    )
    assert first and first["created"]
    assert await _queue(ctx) == []  # a robot: no auto-reply

    # Our answer from the document, then the citizen's reply to it.
    await EmailService.record_message(
        direction="Outgoing",
        status="Sent",
        subject="Re: Не працює ліхтар",
        sender=BOX,
        recipients=CITIZEN,
        message_id="<ours@grunt.example.com>",
        ref_doctype="MailCase",
        ref_name=first["ref_name"],
        session=ctx.db._session(),
    )
    again = await file_inbound(
        ctx.db._session(),
        mailbox,
        _letter(
            subject="Re: Не працює ліхтар",
            mid="<m2@example.org>",
            in_reply_to="<ours@grunt.example.com>",
            references="<m1@example.org> <ours@grunt.example.com>",
        ),
    )
    assert again and not again["created"]
    assert (again["ref_doctype"], again["ref_name"]) == ("MailCase", first["ref_name"])
    assert await ctx.db.count("MailCase") == 1
    assert await _queue(ctx) == []  # auto-reply only for a new document


@pytest.mark.asyncio
async def test_mailbox_without_append_to_only_keeps_the_letter(ctx, mailbox):
    plain = {**mailbox, "append_to": None}
    filed = await file_inbound(ctx.db._session(), plain, _letter())
    assert filed and filed["ref_doctype"] is None and not filed["created"]
    assert await ctx.db.count("MailCase") == 0


@pytest.mark.asyncio
async def test_append_to_needs_a_doctype_that_takes_mail(ctx, mailbox):
    with pytest.raises(ERRORS):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "x@grunt.example.com", "append_to": "MailPlain"}
        )


@pytest.mark.asyncio
async def test_letter_from_document_threads_and_shows_on_timeline(ctx, mailbox, db_session, engine):
    import grunt

    filed = await file_inbound(ctx.db._session(), mailbox, _letter())
    assert filed
    case = filed["ref_name"]
    [incoming] = await _messages(ctx, direction="Incoming")
    await db_session.commit()
    await ctx.db.bulk_update("EmailQueue", {"status": "Pending"}, {"status": "Sent"})

    agent = make_user(AGENT, roles=["Case Agent"])
    async with grunt.context(db_session, engine, agent):
        start = await email_api.compose_context(
            doctype="MailCase", doc_id=case, reply_to=incoming["name"]
        )
        assert start["to"] == f"Громадянин <{CITIZEN}>"
        assert start["subject"] == "Re: Не працює ліхтар"
        assert start["account"] == mailbox["name"]
        assert "Служба підтримки" in start["signatures"][mailbox["name"]]
        assert start["can_print"] is False

        sent = await email_api.send_email(
            doctype="MailCase",
            doc_id=case,
            to=CITIZEN,
            cc="boss@grunt.example.com",
            bcc="archive@grunt.example.com",
            subject=start["subject"],
            content="<p>Передали в ЖЕК.</p><script>x()</script>",
            reply_to=incoming["name"],
        )
        with pytest.raises(ERRORS):  # the PDF needs print access
            await email_api.send_email(
                doctype="MailCase",
                doc_id=case,
                to=CITIZEN,
                subject="s",
                content="c",
                attach_print=True,
            )
        with pytest.raises(ERRORS):
            await email_api.send_email(
                doctype="MailCase", doc_id=case, to="not-an-address", subject="s", content="c"
            )
    await db_session.commit()

    queued = [q for q in await _queue(ctx) if q["cc"]]
    assert len(queued) == 1
    q = queued[0]
    assert (q["recipient"], q["cc"], q["bcc"]) == (
        CITIZEN,
        "boss@grunt.example.com",
        "archive@grunt.example.com",
    )
    assert "<script>" not in q["content"]
    assert q["in_reply_to"] == "<m1@example.org>"
    assert q["message_references"] == "<m1@example.org>"

    # The worker sends it: the timeline's "Queued" row becomes "Sent".
    await EmailService.record_message(
        direction="Outgoing",
        status="Sent",
        message_id=q["message_id"],
        session=ctx.db._session(),
    )
    [row] = await _messages(ctx, name=sent["message"])
    assert row["status"] == "Sent"

    viewer = make_user("viewer@grunt.example.com", roles=["Case Viewer"])
    async with grunt.context(db_session, engine, viewer):
        timeline = await history_api.get_timeline(doctype="MailCase", doc_id=case)
        with pytest.raises(ERRORS):  # reading is not writing
            await email_api.compose_context(doctype="MailCase", doc_id=case)
    letters = [i for i in timeline if i["type"] == "email"]
    assert [(i["direction"], i["is_auto_reply"]) for i in letters] == [
        ("Incoming", False),
        ("Outgoing", True),
        ("Outgoing", False),
    ]
    assert letters[0]["user"] == CITIZEN


def test_envelope_has_bcc_and_always_bcc_but_headers_do_not():
    msg = EmailMessage()
    msg["To"] = "A <a@x.org>, b@x.org"
    msg["Cc"] = "c@x.org"
    rcpt = envelope_recipients(msg, {"bcc": "d@x.org, A@x.org"}, {"always_bcc": "archive@x.org"})
    assert rcpt == ["a@x.org", "b@x.org", "c@x.org", "d@x.org", "archive@x.org"]
    assert msg["Bcc"] is None


@pytest.mark.asyncio
async def test_unanswered_letters_notify_assignees_else_the_group(ctx, mailbox):
    session = ctx.db._session()
    one = await file_inbound(session, mailbox, _letter(mid="<u1@example.org>"))
    two = await file_inbound(session, mailbox, _letter(mid="<u2@example.org>", subject="Яма"))
    three = await file_inbound(session, mailbox, _letter(mid="<u3@example.org>", subject="Сміття"))
    assert one and two and three
    await ctx.new_doc(
        "ToDo",
        {
            "description": "Розібратися",
            "reference_doctype": "MailCase",
            "reference_id": one["ref_name"],
            "assigned_to": AGENT,
            "status": "Open",
        },
    )
    # The third one is answered (an auto-reply alone is no answer).
    await EmailService.record_message(
        direction="Outgoing",
        status="Sent",
        message_id="<answer@grunt.example.com>",
        ref_doctype="MailCase",
        ref_name=three["ref_name"],
        session=session,
    )
    now = datetime.now(UTC)
    assert await process_unreplied(session, now=now) == 0  # not 30 minutes yet

    later = now + timedelta(minutes=31)
    assert await process_unreplied(session, now=later) == 2
    logs = await ctx.db.get_all(
        "NotificationLog", fields=["user", "ref_doctype", "doc_id"], limit=None
    )
    assert sorted((r["user"], r["doc_id"]) for r in logs) == sorted(
        [(AGENT, one["ref_name"]), (DUTY, two["ref_name"])]
    )
    incoming = await _messages(ctx, direction="Incoming")
    assert all(m["unreplied_checked"] for m in incoming)
    assert await process_unreplied(session, now=later) == 0  # once per letter


class _Resp:
    def __init__(self, result, lines):
        self.result, self.lines = result, lines


class FakeImap:
    """Enough of aioimaplib for pull_emails: one folder of letters by UID."""

    def __init__(self, letters: dict[int, bytes], unseen: set[int], validity="7"):
        self.letters, self.unseen, self.validity = letters, unseen, validity
        self.flags_changed = False

    def __call__(self, host, port):
        return self

    async def wait_hello_from_server(self):
        pass

    async def login(self, user, password):
        return _Resp("OK", [])

    async def select(self, mailbox):
        return _Resp("OK", [f"OK [UIDVALIDITY {self.validity}] UIDs valid".encode()])

    async def uid_search(self, criteria, charset=None):
        if criteria == "UNSEEN":
            found = sorted(self.unseen)
        elif criteria == "ALL":
            found = sorted(self.letters)
        else:
            start = int(criteria.split()[1].split(":")[0])
            found = [u for u in sorted(self.letters) if u >= start] or [max(self.letters)]
        return _Resp("OK", [" ".join(map(str, found)).encode(), b"SEARCH completed"])

    async def uid(self, command, uid, what):
        assert "PEEK" in what  # never flips \\Seen
        raw = self.letters[int(uid)]
        head = f"1 FETCH (UID {uid} BODY[] {{{len(raw)}}}".encode()
        return _Resp("OK", [head, bytearray(raw), b")"])

    async def store(self, *args):
        self.flags_changed = True

    async def logout(self):
        pass


def _raw(mid: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["Subject"], msg["Message-ID"] = CITIZEN, mid, mid
    msg.set_content("x")
    return msg.as_bytes()


@pytest.mark.asyncio
async def test_pull_reads_by_uid_without_touching_seen_flags(monkeypatch):
    imap = FakeImap({3: _raw("<a@x>"), 5: _raw("<b@x>"), 9: _raw("<c@x>")}, unseen={5})
    monkeypatch.setattr(inbound.aioimaplib, "IMAP4_SSL", imap)
    account = {
        "enable_incoming": True,
        "imap_server": "imap.example.org",
        "email_address": BOX,
        "smtp_password": "pw",
        "imap_folders": "INBOX",
    }
    # First run: the unread letters only.
    emails, state = await pull_emails(account)
    assert [e["uid"] for e in emails] == [5]
    assert state == {"INBOX": {"uidvalidity": "7", "last_uid": 5}}

    # Next run: everything after the last UID (9), not the old ones again.
    emails, state = await pull_emails({**account, "imap_state": state})
    assert [e["subject"] for e in emails] == ["<c@x>"]
    assert state["INBOX"]["last_uid"] == 9
    emails, state = await pull_emails({**account, "imap_state": state})
    assert emails == []  # "10:*" still matches 9 - filtered out

    # The server renumbered the folder: start over from the unread ones.
    imap.validity = "8"
    emails, _state = await pull_emails({**account, "imap_state": state})
    assert [e["uid"] for e in emails] == [5]
    assert not imap.flags_changed


@pytest.mark.asyncio
async def test_file_one_fires_the_hook_and_imap_state_is_saved(ctx, mailbox, monkeypatch):
    from grunt.email import tasks

    seen = []

    async def fake_fire(event, **kwargs):
        seen.append((event, kwargs["filed"]["created"]))

    monkeypatch.setattr(tasks, "fire", fake_fire)
    session = ctx.db._session()
    await tasks._file_one(session, mailbox, _letter(mid="<hook@example.org>"))
    await tasks._file_one(session, mailbox, _letter(mid="<hook@example.org>"))  # re-read
    assert seen == [("inbound_email", True)]

    state = {"INBOX": {"uidvalidity": "7", "last_uid": 42}}
    await ctx.db.set_value("EmailAccount", mailbox["name"], "imap_state", state)
    assert (await ctx.get_doc("EmailAccount", mailbox["name"]))["imap_state"] == state
