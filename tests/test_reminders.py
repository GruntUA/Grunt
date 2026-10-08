"""Personal reminders: "remind me about this document at …"."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.tasks import reminders
from tests.support import make_user

NOTE = {
    "name": "RemNote",
    "label": "Rem Note",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "title_field": "title",
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Reader", "read": True},
    ],
}

ANN = "ann@example.com"
BEN = "ben@example.com"
ERRORS = (ApplicationError, HTTPException)


@pytest.fixture
async def note(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**NOTE, "__is_new": True})
    for email in (ANN, BEN):
        await ctx.new_doc("User", {"email": email, "first_name": email[:3], "last_name": "R"})
    doc = await ctx.new_doc("RemNote", {"title": "Budget 2027"})
    await ctx.db._session().commit()
    return doc


@pytest.fixture
def as_user(db_session, engine):
    import grunt

    def enter(email, roles=("Reader",)):
        return grunt.context(db_session, engine, make_user(email, roles=list(roles)))

    return enter


def _in(minutes: int) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


async def _subjects(ctx, user):
    rows = await ctx.db.get_all(
        "Notification", filters={"user": user}, fields=["subject", "message"]
    )
    return [(r["subject"], r["message"]) for r in rows]


@pytest.mark.asyncio
async def test_remind_me_and_delivery(ctx, note, as_user, db_session):
    from grunt import _
    from grunt.document.base import Document

    async with as_user(ANN):
        r = await Document.add_reminder(
            doctype="RemNote", doc_id=note["name"], remind_at=_in(30), description="Check totals"
        )
        sidebar = await Document.get_sidebar(doctype="RemNote", doc_id=note["name"])
    await db_session.commit()
    assert [x["description"] for x in sidebar["reminders"]] == ["Check totals"]

    async with ctx.system_context(db_session):
        assert await reminders.process_due() == 0  # not yet
        later = datetime.now(UTC) + timedelta(minutes=31)
        assert await reminders.process_due(later) == 1
        assert await reminders.process_due(later) == 0  # sent once

    subject = _("Reminder: %(title)s") % {"title": "Budget 2027"}
    assert await _subjects(ctx, ANN) == [(subject, "Check totals")]
    assert (await ctx.db.get_value("Reminder", r["name"], "notified")) in (True, 1)

    # Sent reminders leave the sidebar.
    async with as_user(ANN):
        sidebar = await Document.get_sidebar(doctype="RemNote", doc_id=note["name"])
    assert sidebar["reminders"] == []


@pytest.mark.asyncio
async def test_reminders_are_private(ctx, note, as_user, db_session):
    import grunt
    from grunt.document.base import Document

    async with as_user(ANN):
        r = await Document.add_reminder(doctype="RemNote", doc_id=note["name"], remind_at=_in(10))
    await db_session.commit()

    async with as_user(BEN):
        assert await grunt.get_list("Reminder", limit=10) == []
        sidebar = await Document.get_sidebar(doctype="RemNote", doc_id=note["name"])
        assert sidebar["reminders"] == []
        with pytest.raises(ERRORS):
            await grunt.save_doc("Reminder", r["name"], {"description": "hijack"})


@pytest.mark.asyncio
async def test_validation_and_rescheduling(ctx, note, as_user, db_session):
    import grunt
    from grunt.document.base import Document

    async with as_user(ANN):
        with pytest.raises(ERRORS):  # in the past
            await Document.add_reminder(doctype="RemNote", doc_id=note["name"], remind_at=_in(-60))
    async with as_user("nobody@example.com", roles=()):
        with pytest.raises(ERRORS):  # cannot read the document
            await Document.add_reminder(doctype="RemNote", doc_id=note["name"], remind_at=_in(5))

    async with as_user(ANN):
        r = await Document.add_reminder(doctype="RemNote", doc_id=note["name"], remind_at=_in(1))
    await db_session.commit()
    async with ctx.system_context(db_session):
        assert await reminders.process_due(datetime.now(UTC) + timedelta(minutes=2)) == 1

    # Snoozing (a new time) arms it again.
    async with as_user(ANN):
        await grunt.save_doc("Reminder", r["name"], {"remind_at": _in(60)})
    await db_session.commit()
    assert (await ctx.db.get_value("Reminder", r["name"], "notified")) in (False, 0)
