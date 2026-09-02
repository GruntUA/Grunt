"""HTML mail must be delivered as ``text/html``, not raw markup in a plain body."""

from __future__ import annotations

import pytest

from grunt.email.service import EmailService, email_service


@pytest.mark.asyncio
async def test_queue_email_stores_html_flag_and_plain_alternative(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        record_id = await email_service.queue_email(
            session=ctx.db._session(),
            to="user@example.com",
            subject="Код для входу",
            body="Ваш код: 123456",
            html_body="<p>Ваш код: <b>123456</b></p>",
        )
        assert record_id

        row = (
            await ctx.db.get_all(
                "EmailQueue",
                filters={"name": record_id},
                fields=["content", "text_content", "is_html"],
                limit=1,
            )
        )[0]

    assert row["is_html"]
    assert row["content"] == "<p>Ваш код: <b>123456</b></p>"
    assert row["text_content"] == "Ваш код: 123456"


@pytest.mark.asyncio
async def test_send_now_builds_html_alternative():
    """A queue row with ``is_html`` produces a real ``text/html`` MIME part."""
    from unittest.mock import AsyncMock, patch

    account = {
        "enable_outgoing": True,
        "email_address": "out@example.com",
        "smtp_server": "localhost",
        "smtp_port": 587,
        "smtp_user": "out@example.com",
        "smtp_password": "x",
    }
    message = {
        "subject": "Код для входу",
        "recipient": "user@example.com",
        "content": "<p>Ваш код: <b>123456</b></p>",
        "text_content": "Ваш код: 123456",
        "is_html": True,
    }

    sent: list = []

    class _FakeSMTP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def login(self, *a):
            pass

        async def send_message(self, msg):
            sent.append(msg)

    with (
        patch("grunt.email.service.aiosmtplib.SMTP", lambda **kw: _FakeSMTP()),
        patch.object(EmailService, "_log_outgoing", AsyncMock()),
    ):
        await EmailService.send_now(account, message)

    assert sent, "send_message was not called"
    msg = sent[0]
    assert msg.is_multipart()
    types = {p.get_content_type() for p in msg.walk()}
    assert "text/html" in types
    assert "text/plain" in types
    html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    assert "<b>123456</b>" in html_part.get_content()
