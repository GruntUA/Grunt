"""UserGroup (FRAPPE_GAP #12): members once and active only; the manager may
change the members, not appoint a manager; a group gives no permissions; a
notification to a group; an assignment rule to a group."""

import pytest
from fastapi import HTTPException

from grunt.api.v1.meta import save_doctype
from grunt.notification.service import notification_service
from grunt.permissions.groups import group_emails
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


async def test_manager_whose_user_name_is_not_the_email(ctx, group, db_session, engine):
    """The rule matches the manager's email, not their User name."""
    await ctx.rename_doc("User", ANN, "ann-renamed")
    await ctx.db._session().commit()
    assert (await ctx.get_doc("UserGroup", group))["manager"] == "ann-renamed"

    async def add_cid_only(grunt):
        return await grunt.save_doc("UserGroup", group, {"users": [{"user": CID}]})

    await _as(db_session, engine, ANN, add_cid_only)
    assert await group_emails([group]) == [CID]


async def test_group_name_without_closing_bracket(ctx, group):
    with pytest.raises(HTTPException):
        await ctx.new_doc("UserGroup", {"group_name": "Desk] East"})


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


# Step 2: shares, assigning by hand, @mentions.


async def _share(ctx, ticket: str, group: str) -> None:
    await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "GroupTicket", "reference_id": ticket, "user_group": group},
    )
    await ctx.db._session().commit()


async def _reads(db_session, engine, email, ticket) -> bool:
    import grunt

    async with grunt.context(db_session, engine, make_user(email, roles=[])):
        try:
            await grunt.get_doc("GroupTicket", ticket)
        except HTTPException:
            return False
        rows = await grunt.get_list("GroupTicket", fields=["name"])
        return [r["name"] for r in rows] == [ticket]


async def test_share_with_a_group_reaches_its_members(ctx, group, db_session, engine):
    ticket = (await ctx.new_doc("GroupTicket", {"subject": "x"}))["name"]
    await ctx.db._session().commit()
    assert not await _reads(db_session, engine, BOB, ticket)

    await _share(ctx, ticket, group)
    assert await _reads(db_session, engine, BOB, ticket)
    assert not await _reads(db_session, engine, ANN, ticket)  # the manager isn't a member

    # Someone added later gets the access too; someone removed loses it.
    await ctx.save_doc("UserGroup", group, {"users": [{"user": CID}, {"user": ANN}]})
    await ctx.db._session().commit()
    assert await _reads(db_session, engine, ANN, ticket)
    assert not await _reads(db_session, engine, BOB, ticket)


async def test_share_with_a_group_tells_its_members(ctx, group, standard_notifications):
    ticket = (await ctx.new_doc("GroupTicket", {"subject": "x"}))["name"]
    await _share(ctx, ticket, group)
    rows = await ctx.db.get_all("NotificationLog", fields=["user"], limit=10)
    assert sorted(r["user"] for r in rows) == [BOB, CID]


async def test_share_names_one_target(ctx, group):
    ticket = (await ctx.new_doc("GroupTicket", {"subject": "x"}))["name"]
    with pytest.raises(HTTPException):
        await ctx.new_doc(
            "SharedWith",
            {
                "reference_doctype": "GroupTicket",
                "reference_id": ticket,
                "user_group": group,
                "everyone": 1,
            },
        )
    with pytest.raises(HTTPException):
        await _share(ctx, ticket, "No such group")


async def test_access_inspector_names_the_group(ctx, group):
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.explain import _shares

    ticket = (await ctx.new_doc("GroupTicket", {"subject": "x"}))["name"]
    await _share(ctx, ticket, group)
    meta = await doctype_registry.get_meta("GroupTicket")
    found = await _shares(BOB, meta, "read", {"name": ticket})
    assert [(s["via"], s["user_group"]) for s in found] == [("group", group)]


async def test_assign_to_a_group_skips_those_assigned(ctx, group):
    from grunt.api.v1.document.collaboration import assign_to_group

    ticket = (await ctx.new_doc("GroupTicket", {"subject": "x"}))["name"]
    await ctx.new_doc(
        "ToDo",
        {
            "reference_doctype": "GroupTicket",
            "reference_id": ticket,
            "assigned_to": BOB,
            "status": "Open",
            "description": "Вже призначено",
        },
    )
    result = await assign_to_group("GroupTicket", ticket, group, "Розгляньте")
    assert result == {"assigned": [CID]}
    rows = await ctx.db.get_all(
        "ToDo",
        filters={"reference_doctype": "GroupTicket", "reference_id": ticket},
        fields=["assigned_to", "description"],
        limit=None,
    )
    assert sorted((r["assigned_to"], r["description"]) for r in rows)[1] == (CID, "Розгляньте")
    assert await assign_to_group("GroupTicket", ticket, group) == {"assigned": []}


async def test_mention_a_group(ctx, group, standard_notifications, db_session, engine):
    import grunt
    from grunt.api.v1.document.collaboration import add_comment

    ticket = (await ctx.new_doc("GroupTicket", {"subject": "x"}))["name"]
    await ctx.db._session().commit()
    async with grunt.context(db_session, engine, make_user(BOB, roles=["System Manager"])):
        await add_comment("GroupTicket", ticket, f"Погляньте, @[{group}] і @{ANN}")
    await db_session.commit()
    rows = await ctx.db.get_all("NotificationLog", fields=["user"], limit=10)
    # Bob wrote it - he isn't told about his own mention.
    assert sorted(r["user"] for r in rows) == [ANN, CID]
