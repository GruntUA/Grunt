"""EmailQueue: priority, send-after, retries of temporary failures, and
unsubscribing from notification emails (List-Unsubscribe, the page, the
email channel and the digest skipping the address)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest
from fastapi import HTTPException

from grunt.email import unsubscribe as unsub
from grunt.email.service import EmailService, email_service, is_temporary
from grunt.email.tasks import due_emails
from grunt.integrations.oauth import OAuthError

OUT = "out@example.com"
READER = "Reader@Example.com"


class _Request:
    def __init__(self, method: str):
        self.method = method


@pytest.fixture
async def outbox(ctx):
    await ctx.new_doc("EmailAccount", {"email_address": OUT, "enable_outgoing": True})
    await ctx.db._session().commit()


async def _queue(ctx, subject: str, **kwargs) -> str:
    rid = await email_service.queue_email(
        session=ctx.db._session(), to="user@example.com", subject=subject, body="b", **kwargs
    )
    await ctx.db._session().commit()
    return rid


async def _rule(ctx) -> None:
    await ctx.new_doc(
        "Notification",
        {
            "name": "Unsubscribe test rule",
            "event": "code",
            "event_key": "grunt.todo.assigned",
            "recipients": [{"kind": "Email", "email": READER}],
            "channels": [{"channel": "email"}],
        },
    )


@pytest.fixture
def worker(monkeypatch):
    """Run ``process_email_queue`` on the test database."""
    import conftest as _cf
    from grunt.email import tasks as email_tasks

    monkeypatch.setattr(email_tasks.site_manager, "get_active_site", lambda: "test", raising=False)
    monkeypatch.setattr(
        email_tasks.site_manager,
        "get_session_maker",
        lambda _s: _cf.TestSessionLocal,
        raising=False,
    )
    monkeypatch.setattr(
        email_tasks.site_manager, "get_engine", lambda _s: _cf.test_engine, raising=False
    )
    return email_tasks.process_email_queue


# Priority and send-after


@pytest.mark.asyncio
async def test_due_emails_by_priority_then_age_and_not_before_time(ctx, outbox):
    low = await _queue(ctx, "low", priority="Low")
    normal = await _queue(ctx, "normal")
    legacy = await _queue(ctx, "legacy")
    await ctx.db.set_value("EmailQueue", legacy, "priority", None)  # queued before priorities
    high = await _queue(ctx, "high", priority="High")
    later = await _queue(
        ctx, "later", priority="High", send_after=datetime.now(UTC) + timedelta(hours=1)
    )
    past = await _queue(ctx, "past", send_after=datetime.now(UTC) - timedelta(minutes=1))
    await ctx.db._session().commit()

    names = [r["name"] for r in await due_emails(limit=100)]
    assert later not in names
    assert names[0] == high
    assert names.index(normal) < names.index(low)
    assert {legacy, past} <= set(names[1:-1])
    assert [r["name"] for r in await due_emails(limit=2)] == [high, normal]


def test_temporary_and_permanent_failures():
    assert is_temporary(aiosmtplib.SMTPServerDisconnected("gone"))
    assert is_temporary(TimeoutError())
    assert is_temporary(aiosmtplib.SMTPResponseException(451, "try later"))
    assert not is_temporary(aiosmtplib.SMTPResponseException(550, "no such user"))
    assert not is_temporary(aiosmtplib.SMTPAuthenticationError(535, "bad credentials"))
    assert not is_temporary(ValueError("Outgoing email is disabled"))
    assert not is_temporary(RuntimeError("a bug"))
    assert is_temporary(OAuthError("could not renew"))
    refused = aiosmtplib.SMTPRecipientsRefused(
        [
            aiosmtplib.SMTPRecipientRefused(550, "no", "a@x"),
            aiosmtplib.SMTPRecipientRefused(450, "busy", "b@x"),
        ]
    )
    assert not is_temporary(refused)


# Retries


@pytest.mark.asyncio
async def test_temporary_failure_is_retried_later_then_gives_up(ctx, outbox, worker, monkeypatch):
    rid = await _queue(ctx, "flaky")
    monkeypatch.setattr(
        EmailService,
        "send_now",
        staticmethod(AsyncMock(side_effect=aiosmtplib.SMTPServerDisconnected("gone"))),
    )
    await worker()
    row = await ctx.db.get_value("EmailQueue", rid, ["status", "retry", "send_after"], as_dict=True)
    assert row and row["status"] == "Pending" and row["retry"] == 1
    send_after = row["send_after"]
    if send_after.tzinfo is None:
        send_after = send_after.replace(tzinfo=UTC)
    assert send_after > datetime.now(UTC)

    await worker()  # not due yet - untouched
    assert await ctx.db.get_value("EmailQueue", rid, "retry") == 1

    # The last allowed attempt fails too: an error, for good.
    await ctx.db.set_value("EmailQueue", rid, {"retry": 5, "send_after": None})
    await ctx.db._session().commit()
    await worker()
    assert await ctx.db.get_value("EmailQueue", rid, "status") == "Error"


@pytest.mark.asyncio
async def test_permanent_failure_is_an_error_at_once(ctx, outbox, worker, monkeypatch):
    rid = await _queue(ctx, "bounced")
    monkeypatch.setattr(
        EmailService,
        "send_now",
        staticmethod(AsyncMock(side_effect=aiosmtplib.SMTPResponseException(550, "no such user"))),
    )
    await worker()
    row = await ctx.db.get_value("EmailQueue", rid, ["status", "retry"], as_dict=True)
    assert row and row["status"] == "Error" and not row["retry"]


@pytest.mark.asyncio
async def test_manual_retry_starts_over(ctx, outbox):
    from grunt.api.v1.email import retry_item

    rid = await _queue(ctx, "x")
    await ctx.db.set_value(
        "EmailQueue", rid, {"status": "Error", "retry": 5, "send_after": datetime.now(UTC)}
    )
    await retry_item(queue_id=rid)
    row = await ctx.db.get_value("EmailQueue", rid, ["status", "retry", "send_after"], as_dict=True)
    assert row and (row["status"], row["retry"], row["send_after"]) == ("Pending", 0, None)


# Unsubscribing


@pytest.mark.asyncio
async def test_send_now_adds_one_click_unsubscribe_headers():
    account = {"enable_outgoing": True, "email_address": OUT, "smtp_server": "localhost"}
    url = "https://site.example/unsub?x=1"
    smtp = AsyncMock()
    smtp.__aenter__.return_value = smtp
    with (
        patch("grunt.email.service.aiosmtplib.SMTP", return_value=smtp),
        patch.object(EmailService, "_log_outgoing", AsyncMock(return_value=None)),
    ):
        await EmailService.send_now(
            account, {"subject": "s", "recipient": "a@x", "content": "c", "unsubscribe_url": url}
        )
    sent = smtp.send_message.call_args.args[0]
    assert sent["List-Unsubscribe"] == f"<{url}>"
    assert sent["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_unsubscribe_link_is_signed_for_the_address():
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(unsub.unsubscribe_url(READER, "Unsubscribe test rule")).query)
    assert query["email"] == ["reader@example.com"]
    assert unsub.valid_token("reader@example.com", query["token"][0])
    assert not unsub.valid_token("someone@example.com", query["token"][0])
    assert query["notification"] == ["Unsubscribe test rule"]


@pytest.mark.asyncio
async def test_page_asks_then_post_unsubscribes(ctx):
    await _rule(ctx)
    token = unsub.make_token(READER)

    bad = await unsub.unsubscribe(email=READER, token="forged", request=_Request("POST"))  # type: ignore[arg-type]
    assert b"method='post'" not in bad.body and not await unsub.is_unsubscribed(READER)

    page = await unsub.unsubscribe(
        email=READER,
        token=token,
        notification="Unsubscribe test rule",
        request=_Request("GET"),  # type: ignore[arg-type]
    )
    assert b"method='post'" in page.body
    assert not await unsub.is_unsubscribed(READER, "Unsubscribe test rule")

    await unsub.unsubscribe(
        email=READER,
        token=token,
        notification="Unsubscribe test rule",
        request=_Request("POST"),  # type: ignore[arg-type]
    )
    assert await unsub.is_unsubscribed(READER, "Unsubscribe test rule")
    assert await unsub.is_unsubscribed("reader@example.com", "Unsubscribe test rule")
    assert not await unsub.is_unsubscribed(READER, "Other rule")
    assert not await unsub.is_unsubscribed(READER)  # not from all

    await unsub.unsubscribe(email=READER, token=token, request=_Request("POST"))  # type: ignore[arg-type]
    assert await unsub.is_unsubscribed(READER, "Other rule")
    assert await unsub.is_unsubscribed(READER)


@pytest.mark.asyncio
async def test_email_channel_skips_unsubscribed_and_links_the_rest(ctx, outbox):
    from grunt.notification.channels import EmailChannel, Message

    await _rule(ctx)
    message = Message(
        subject="Нове завдання", body="b", html="<p>b</p>", notification="Unsubscribe test rule"
    )
    session = ctx.db._session()

    outcome = await EmailChannel().send(session, READER, message, delivery="dl-1")
    assert outcome.status == "Queued"
    row = await ctx.db.get_value(
        "EmailQueue",
        outcome.links["email_queue"],
        ["priority", "unsubscribe_url", "content", "text_content"],
        as_dict=True,
    )
    assert row and row["priority"] == "Low" and row["unsubscribe_url"]
    assert (
        "Unsubscribe+test+rule" in row["unsubscribe_url"]
        or "Unsubscribe%20test%20rule" in row["unsubscribe_url"]
    )
    assert row["unsubscribe_url"].replace("&", "&amp;") in row["content"]
    assert row["unsubscribe_url"] in row["text_content"]

    # The dispatcher skips who unsubscribed (NotificationPreference, channel email).
    from grunt.notification.delivery import deliver

    await unsub.add(READER, "Unsubscribe test rule")
    report = await deliver(session, [READER], message, ["email"])
    assert report.counts == {"Skipped": 1}

    # A mandatory rule's letter: no link, and the unsubscribe doesn't stop it.
    message.mandatory = True
    report = await deliver(session, [READER], message, ["email"])
    assert report.counts == {"Queued": 1}
    mandatory = await EmailChannel().send(session, READER, message, delivery="dl-3")
    assert not await ctx.db.get_value(
        "EmailQueue", mandatory.links["email_queue"], "unsubscribe_url"
    )


@pytest.mark.asyncio
async def test_letters_without_a_rule_have_no_unsubscribe(ctx, outbox):
    rid = await _queue(ctx, "Sign-in code", priority="High")
    assert not await ctx.db.get_value("EmailQueue", rid, "unsubscribe_url")


# Send at


@pytest.mark.asyncio
async def test_send_after_parsing():
    from grunt.api.v1.email import _parse_send_after

    future = datetime.now(UTC) + timedelta(hours=2)
    assert _parse_send_after(future.isoformat().replace("+00:00", "Z")) == future
    naive = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None, microsecond=0)
    assert _parse_send_after(naive.isoformat()) == naive.replace(tzinfo=UTC)
    assert _parse_send_after((datetime.now(UTC) - timedelta(hours=1)).isoformat()) is None
    assert _parse_send_after(None) is None
    with pytest.raises(HTTPException):
        _parse_send_after("tomorrow")
