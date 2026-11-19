"""UserGroup (FRAPPE_GAP #12): members once and active only; the manager may
change the members, not appoint a manager; a group gives no permissions; a
notification to a group; an assignment rule to a group."""

import pytest
from fastapi import HTTPException

from grunt.api.v1.meta import save_doctype
from grunt.auth.doctypes.UserGroup.user_group import group_emails
from grunt.notification.service import notification_service
from tests.support import make_user

ANN, BOB, CID = "ann@grunt.example.com", "bob@grunt.example.com", "cid@grunt.example.com"


@pytest.fixture
async def group(ctx):
    await save_doctype(
        doctype_data={
            "name": "GroupTicket",
            "label": "Ticket",
            "module": "core",
            "__is_new": True,
            "fields": [{"fieldname": "subject", "label": "Subject", "fieldtype": "Data"}],
            "permissions": [{"role": "System Manager", "actions": ["read", "write", "create"]}],
        }
    )
    for email in (ANN, BOB, CID):
        await ctx.new_doc("User", {"email": email, "first_name": email[:3], "last_name": "T"})
    await ctx.new_doc(
        "UserGroup",
        {
            "group_name": "Desk",
            "manager": ANN,
            "users": [{"user": BOB}, {"user": CID}, {"user": BOB}],
        },
    )
    await ctx.db._session().commit()
    return "Desk"


async def test_members_once_and_active_only(ctx, group):
    doc = await ctx.get_doc("UserGroup", group)
    assert [r["user"] for r in doc["users"]] == [BOB, CID]
    assert await group_emails([group]) == [BOB, CID]

    await ctx.save_doc("User", CID, {"is_active": False})
    assert await group_emails([group]) == [BOB]


async def _as(db_session, engine, email, fn):
    import grunt

    async with grunt.context(db_session, engine, make_user(email, roles=[])):
        return await fn(grunt)


async def test_manager_changes_members_not_the_manager(ctx, group, db_session, engine):
    async def add_ann(grunt):
        return await grunt.save_doc("UserGroup", group, {"users": [{"user": BOB}, {"user": ANN}]})

    await _as(db_session, engine, ANN, add_ann)
    assert await group_emails([group]) == [BOB, ANN]

    async def hand_over(grunt):
        return await grunt.save_doc("UserGroup", group, {"manager": BOB})

    with pytest.raises(HTTPException) as exc:
        await _as(db_session, engine, ANN, hand_over)
    assert exc.value.status_code == 403


async def test_others_may_read_not_change(ctx, group, db_session, engine):
    async def read(grunt):
        return await grunt.get_doc("UserGroup", group)

    assert (await _as(db_session, engine, BOB, read))["group_name"] == group

    async def change(grunt):
        return await grunt.save_doc("UserGroup", group, {"users": []})

    with pytest.raises(HTTPException) as exc:
        await _as(db_session, engine, BOB, change)
    assert exc.value.status_code == 403


async def test_notification_to_a_group(ctx, group):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rule = await ctx.new_doc(
            "Notification",
            {
                "ref_doctype": "GroupTicket",
                "event": "after_save",
                "recipients": [{"kind": "User group", "user_group": group}],
                "channels": [{"channel": "in_app"}],
                "subject_template": "{{ doc.subject }}",
                "message_template": "",
            },
        )
        sent = await notification_service.apply_rule(
            ctx.db._session(),
            dict(rule),
            "GroupTicket",
            {"name": "T-1", "owner": ANN, "subject": "x"},
            ANN,
            "after_save",
        )
        rows = await ctx.db.get_all("NotificationDelivery", fields=["recipient"], limit=10)
    assert sent == 2
    assert sorted(r["recipient"] for r in rows) == [BOB, CID]


async def test_assignment_rule_to_a_group(ctx, group):
    await ctx.new_doc(
        "AssignmentRule",
        {"doctype_target": "GroupTicket", "enabled": True, "assign_to_group": group},
    )
    await ctx.db._session().commit()
    ticket = await ctx.new_doc("GroupTicket", {"subject": "x"})
    await ctx.db._session().commit()
    rows = await ctx.db.get_all(
        "ToDo",
        filters={"reference_doctype": "GroupTicket", "reference_id": ticket["name"]},
        fields=["assigned_to"],
        limit=None,
    )
    assert sorted(r["assigned_to"] for r in rows) == [BOB, CID]
