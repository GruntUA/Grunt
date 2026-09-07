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


@pytest.mark.asyncio
async def test_reassigning_a_todo_notifies_the_new_assignee(ctx):
    other = "other@example.com"
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        todo = await ctx.new_doc(
            "ToDo",
            {
                "description": "Звірити залишки",
                "reference_doctype": "User",
                "reference_id": "asset-7",
                "assigned_to": ASSIGNEE,
                "status": "Open",
            },
        )
        await ctx.save_doc("ToDo", todo["name"], {"assigned_to": other})

        first = await _notifs_for(ctx, ASSIGNEE)
        second = await _notifs_for(ctx, other)

    assert len(first) == 1  # only the original create ping — not re-pinged
    assert len(second) == 1  # the reassignment ping
    assert "User asset-7" in second[0]["subject"]


@pytest.mark.asyncio
async def test_closing_a_todo_stamps_completion_and_notifies_the_assigner(ctx):
    assigner = "boss@example.com"
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.db._session().commit()

        todo = await ctx.new_doc(
            "ToDo",
            {
                "description": "Закрити інвентаризацію",
                "reference_doctype": "User",
                "reference_id": "asset-9",
                "assigned_to": ASSIGNEE,
                "assigned_by": assigner,
                "status": "Open",
            },
        )
        await ctx.save_doc("ToDo", todo["name"], {"status": "Closed"})

        row = await ctx.db.get_value(
            "ToDo", todo["name"], ["status", "completed_on", "completed_by"], as_dict=True
        )
        notifs = await _notifs_for(ctx, assigner)
        mails = await _mails_for(ctx, assigner)

    assert row["status"] == "Closed"
    assert row["completed_on"] is not None
    assert row["completed_by"] is not None
    assert len(notifs) == 1
    assert "виконано" in notifs[0]["subject"].lower()
    assert len(mails) == 1


@pytest.mark.asyncio
async def test_reopening_a_todo_clears_the_completion_stamp(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        todo = await ctx.new_doc(
            "ToDo",
            {
                "description": "Тимчасово закрито",
                "reference_doctype": "User",
                "reference_id": "asset-11",
                "assigned_to": ASSIGNEE,
                "status": "Open",
            },
        )
        await ctx.save_doc("ToDo", todo["name"], {"status": "Closed"})
        await ctx.save_doc("ToDo", todo["name"], {"status": "Open"})

        row = await ctx.db.get_value(
            "ToDo", todo["name"], ["status", "completed_on", "completed_by"], as_dict=True
        )

    assert row["status"] == "Open"
    assert row["completed_on"] is None
    assert row["completed_by"] is None


@pytest.mark.asyncio
async def test_todo_complete_action_closes_and_stamps(ctx):
    from grunt.actions import run as run_action

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        todo = await ctx.new_doc(
            "ToDo",
            {
                "description": "Через кнопку",
                "reference_doctype": "User",
                "reference_id": "asset-13",
                "assigned_to": ASSIGNEE,
                "status": "Open",
            },
        )
        res = await run_action("ToDo", "todo.complete", todo["name"])
        row = await ctx.db.get_value(
            "ToDo", todo["name"], ["status", "completed_on"], as_dict=True
        )

    assert res["ok"] is True
    assert row["status"] == "Closed"
    assert row["completed_on"] is not None


@pytest.mark.asyncio
async def test_is_overdue_virtual_field(ctx):
    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        past = await ctx.new_doc(
            "ToDo",
            {"description": "Старе", "assigned_to": ASSIGNEE, "status": "Open",
             "due_date": "2020-01-01"},
        )
        future = await ctx.new_doc(
            "ToDo",
            {"description": "Майбутнє", "assigned_to": ASSIGNEE, "status": "Open",
             "due_date": "2999-01-01"},
        )
        done = await ctx.new_doc(
            "ToDo",
            {"description": "Закрите", "assigned_to": ASSIGNEE, "status": "Open",
             "due_date": "2020-01-01"},
        )
        await ctx.save_doc("ToDo", done["name"], {"status": "Closed"})

        p = await ctx.get_doc("ToDo", past["name"])
        f = await ctx.get_doc("ToDo", future["name"])
        d = await ctx.get_doc("ToDo", done["name"])

    assert p["is_overdue"]
    assert not f["is_overdue"]
    assert not d["is_overdue"]


@pytest.mark.asyncio
async def test_due_reminder_sends_one_digest_per_assignee(ctx, monkeypatch):
    import conftest as _cf
    from grunt.tasks import todo_reminders as tr

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        await ctx.new_doc(
            "EmailAccount", {"email_address": "out@example.com", "enable_outgoing": True}
        )
        await ctx.new_doc(
            "ToDo",
            {"description": "Прострочене", "assigned_to": ASSIGNEE, "reference_doctype": "User",
             "reference_id": "a1", "status": "Open", "due_date": "2020-01-01"},
        )
        await ctx.new_doc(
            "ToDo",
            {"description": "Не термінове", "assigned_to": ASSIGNEE, "status": "Open",
             "due_date": "2999-01-01"},
        )
        await ctx.new_doc(
            "ToDo",
            {"description": "Вже закрите", "assigned_to": ASSIGNEE, "status": "Closed",
             "due_date": "2020-01-01"},
        )
        await ctx.db._session().commit()

    monkeypatch.setattr(tr.site_manager, "get_active_site", lambda: "test", raising=False)
    monkeypatch.setattr(
        tr.site_manager, "get_session_maker", lambda _s: _cf.TestSessionLocal, raising=False
    )
    monkeypatch.setattr(
        tr.site_manager, "get_engine", lambda _s: _cf.test_engine, raising=False
    )

    await tr.send_due_reminders()

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        notifs = await _notifs_for(ctx, ASSIGNEE)
        mails = await _mails_for(ctx, ASSIGNEE)

    digests = [n for n in notifs if n["subject"].startswith("Нагадування")]
    assert len(digests) == 1  # one digest, not one per task
    assert "прострочено" in digests[0]["subject"].lower()
    assert "Не термінове" not in digests[0]["message"]  # future task excluded
    assert sum(m["subject"].startswith("Нагадування") for m in mails) == 1


@pytest.mark.asyncio
async def test_sidebar_shows_in_progress_and_overdue_assignees(ctx):
    from grunt.document.base import Document

    async with ctx.system_context(ctx.db._session(), ctx._require_engine()):
        role = await ctx.new_doc("Role", {"role_name": "Sidebar Test Role"})
        ref = {"reference_doctype": "Role", "reference_id": role["name"]}

        await ctx.new_doc(
            "ToDo",
            {**ref, "description": "В роботі й прострочене", "assigned_to": ASSIGNEE,
             "status": "In Progress", "priority": "High", "due_date": "2020-01-01"},
        )
        await ctx.new_doc(
            "ToDo",
            {**ref, "description": "Вже закрите", "assigned_to": "x@example.com",
             "status": "Closed"},
        )

        bundle = await Document.get_sidebar("Role", role["name"])

    assert len(bundle["assignees"]) == 1  # In Progress in, Closed out
    row = bundle["assignees"][0]
    assert row["status"] == "In Progress"
    assert row["is_overdue"] is True
    assert row["priority"] == "High"
