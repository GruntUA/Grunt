"""Creating a ToDo (an assignment) notifies the person it lands on."""

from __future__ import annotations

import pytest

ASSIGNEE = "assignee@example.com"


async def _notifs_for(ctx, user: str) -> list[dict]:
    return await ctx.db.get_all(
        "Notification",
        filters={"user": user},
        fields=["subject", "message", "doctype", "doc_id"],
        limit=10,
    )


async def _mails_for(ctx, recipient: str) -> list[dict]:
    return await ctx.db.get_all(
        "EmailQueue",
        filters={"recipient": recipient},
        fields=["subject", "content"],
        limit=10,
    )


@pytest.mark.asyncio
async def test_assigning_a_todo_notifies_the_assignee(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        await ctx.new_doc(
            "ToDo",
            {
                "description": "Передати роутер на склад",
                "reference_doctype": "User",
                "reference_id": "someone@example.com",
                "assigned_to": ASSIGNEE,
                "status": "Open",
            },
        )

        notifs = await _notifs_for(ctx, ASSIGNEE)
        mails = await _mails_for(ctx, ASSIGNEE)

    assert len(notifs) == 1
    assert notifs[0]["message"] == "Передати роутер на склад"
    assert "User someone@example.com" in notifs[0]["subject"]
    assert notifs[0]["doctype"] == "User"
    assert len(mails) == 1
    assert "Передати роутер на склад" in mails[0]["content"]


@pytest.mark.asyncio
async def test_placeholder_description_falls_back_to_generic_message(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "ToDo",
            {
                "description": f"Assigned to {ASSIGNEE}",
                "reference_doctype": "User",
                "reference_id": "doc-1",
                "assigned_to": ASSIGNEE,
                "status": "Open",
            },
        )
        notifs = await _notifs_for(ctx, ASSIGNEE)

    assert len(notifs) == 1
    assert notifs[0]["message"] == "Вас призначено відповідальним за User doc-1."


@pytest.mark.asyncio
async def test_self_assignment_does_not_notify(ctx):
    # ctx runs as SYSTEM_USER
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "ToDo",
            {
                "description": "Нагадати собі",
                "reference_doctype": "User",
                "reference_id": "doc-2",
                "assigned_to": SYSTEM_USER.email,
                "status": "Open",
            },
        )
        notifs = await _notifs_for(ctx, SYSTEM_USER.email)

    assert notifs == []


@pytest.mark.asyncio
async def test_auto_assignment_is_idempotent(ctx):
    from grunt.assignment.service import assignment_service

    doc = {"name": "inv-42"}
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await assignment_service._create_todo("Invoice", doc, ASSIGNEE)
        await assignment_service._create_todo("Invoice", doc, ASSIGNEE)

        count = await ctx.db.count(
            "ToDo",
            {"reference_doctype": "Invoice", "reference_id": "inv-42", "assigned_to": ASSIGNEE},
        )
        notifs = await _notifs_for(ctx, ASSIGNEE)

    assert count == 1
    assert len(notifs) == 1
