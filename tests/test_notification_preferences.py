"""Personal notification settings (FRAPPE_GAP #18): NotificationPreference,
mandatory rules, the profile's table, the bell's "Don't send these", the
digest a user chooses and auto-follow."""

from unittest.mock import AsyncMock, patch

import pytest

from grunt.notification import preferences
from grunt.notification.channels import Message
from grunt.notification.delivery import deliver

ME = "me@grunt.example.com"
OTHER = "other@grunt.example.com"
RULE = "Task assigned"

pytestmark = pytest.mark.usefixtures("standard_notifications")


def _message(rule: str | None = RULE, mandatory: bool = False) -> Message:
    return Message(subject="s", body="b", notification=rule, mandatory=mandatory)


async def _user(ctx, email: str = ME, **fields) -> None:
    await ctx.new_doc("User", {"email": email, "first_name": "Me", "last_name": "Test", **fields})


def _as(email: str, admin: bool = False):
    from grunt.auth.doctypes.User.user import User

    roles = ["System Manager"] if admin else []
    return User(doctype="User", data={"email": email, "name": email, "roles": roles})


# The dispatcher


@pytest.mark.asyncio
async def test_turned_off_channel_is_skipped_for_that_person_only(ctx):
    session = ctx.db._session()
    async with ctx.system_context(session, ctx.get_engine()):
        await preferences.set_enabled(ME, RULE, "in_app", False)
        report = await deliver(session, [ME, OTHER], _message(), ["in_app"])
        assert report.counts == {"Skipped": 1, "Sent": 1}
        assert report.reached == {OTHER}
        row = (
            await ctx.db.get_all(
                "NotificationDelivery", filters={"recipient": ME}, fields=["status", "reason"]
            )
        )[0]
        assert row["status"] == "Skipped" and row["reason"]

        # Another rule, and a notification without a rule, still go out.
        assert (await deliver(session, [ME], _message("Other rule"), ["in_app"])).delivered
        assert (await deliver(session, [ME], _message(None), ["in_app"])).delivered


@pytest.mark.asyncio
async def test_all_notifications_row_and_mandatory_rule(ctx):
    session = ctx.db._session()
    async with ctx.system_context(session, ctx.get_engine()):
        await preferences.set_enabled(ME, None, "in_app", False)
        assert (await deliver(session, [ME], _message(None), ["in_app"])).counts == {"Skipped": 1}
        assert (await deliver(session, [ME], _message(), ["in_app"])).counts == {"Skipped": 1}
        mandatory = await deliver(session, [ME], _message(mandatory=True), ["in_app"])
        assert mandatory.counts == {"Sent": 1}


@pytest.mark.asyncio
async def test_rule_marks_its_messages_mandatory(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.db.set_value("Notification", RULE, "is_mandatory", True)
        await preferences.set_enabled(ME, RULE, "in_app", False)
        await ctx.new_doc(
            "ToDo",
            {
                "description": "Перевірити",
                "reference_doctype": "User",
                "reference_id": "someone@example.com",
                "assigned_to": ME,
                "status": "Open",
            },
        )
        bell = await ctx.db.get_all("NotificationLog", filters={"user": ME}, pluck="notification")
    assert bell == [RULE]


# Turning on and off


@pytest.mark.asyncio
async def test_turning_on_one_channel_splits_an_every_channel_row(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await preferences.mute_everywhere(ME, RULE)
        assert await preferences.is_muted(ME, RULE, "email")
        await preferences.set_enabled(
            ME, RULE, "email", True, ["in_app", "web_push", "email", "webhook"]
        )
        assert not await preferences.is_muted(ME, RULE, "email")
        assert await preferences.is_muted(ME, RULE, "in_app")
        assert await preferences.is_muted(ME, RULE, "web_push")
        channels = await ctx.db.get_all(
            "NotificationPreference", filters={"email": ME}, pluck="channel"
        )
        assert None not in channels and "webhook" not in channels

        # Off twice is one row; on again removes it.
        await preferences.set_enabled(ME, RULE, "in_app", False)
        await preferences.set_enabled(ME, RULE, "in_app", True)
        assert not await preferences.is_muted(ME, RULE, "in_app")


# The API


@pytest.mark.asyncio
async def test_api_overview_set_and_mandatory(ctx):
    from grunt.api.v1 import notifications as api

    session = ctx.db._session()
    async with ctx.system_context(session, ctx.get_engine()):
        await _user(ctx)
        await ctx.db.set_value("Notification", "Reminder", "is_mandatory", True)
        await session.commit()

    async with ctx.context(session, ctx.get_engine(), _as(ME)):
        data = await api.get_preferences()
        names = {r["name"]: r for r in data["rules"]}
        assert RULE in names and names["Reminder"]["mandatory"]
        assert "webhook" not in {c["value"] for c in data["channels"]}

        data = await api.set_preference("email", False, RULE)
        assert {"notification": RULE, "channel": "email"} in data["off"]
        data = await api.set_preference("email", "true", RULE)
        assert data["off"] == []

        with pytest.raises(Exception, match="."):
            await api.set_preference("email", False, "Reminder")
        assert not await preferences.is_muted(ME, "Reminder", "email")
        with pytest.raises(Exception, match="webhook"):
            await api.set_preference("webhook", False, RULE)


@pytest.mark.asyncio
async def test_bell_mute_like_turns_the_rule_off_everywhere(ctx):
    from grunt.api.v1 import notifications as api

    session = ctx.db._session()
    async with ctx.system_context(session, ctx.get_engine()):
        await _user(ctx)
        mine = await ctx.new_doc(
            "NotificationLog", {"user": ME, "subject": "s", "message": "m", "notification": RULE}
        )
        theirs = await ctx.new_doc(
            "NotificationLog", {"user": OTHER, "subject": "s", "message": "m", "notification": RULE}
        )
        await session.commit()

    async with ctx.context(session, ctx.get_engine(), _as(ME)):
        with pytest.raises(Exception, match="."):
            await api.mute_like(theirs["name"])
        assert await api.mute_like(mine["name"]) == RULE
        assert await preferences.is_muted(ME, RULE, "email")
        assert not await preferences.is_muted(OTHER, RULE, "email")


# The digest


@pytest.mark.asyncio
async def test_digest_goes_to_who_chose_the_period(ctx):
    from grunt.email import tasks

    session = ctx.db._session()
    async with ctx.system_context(session, ctx.get_engine()):
        await _user(ctx, ME, notification_digest="Weekly")
        await _user(ctx, OTHER)  # the site default: Never
        for user in (ME, OTHER):
            await ctx.new_doc("NotificationLog", {"user": user, "subject": "s", "message": "m"})
        await session.commit()

    sent: list[str] = []

    async def _queue(**kwargs):
        sent.append(kwargs["to"])
        return "q"

    with (
        patch.object(tasks.site_manager, "get_active_site", return_value="test"),
        patch.object(tasks.site_manager, "get_session_maker", return_value=lambda: session),
        patch.object(session, "commit", AsyncMock()),
        patch.object(tasks.email_service, "queue_email", side_effect=_queue),
    ):
        await tasks.send_notification_digest.original_func("daily")
        assert sent == []
        await tasks.send_notification_digest.original_func("weekly")
        assert sent == [ME]


# Auto-follow


async def _follows(ctx, user: str = ME) -> list[str]:
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        return await ctx.db.get_all(
            "DocFollow", filters={"user": user}, pluck="reference_id", limit=None
        )


@pytest.mark.asyncio
async def test_auto_follow_assigned_and_shared(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await _user(ctx, ME, follow_assigned=True, follow_shared=True)
        await _user(ctx, OTHER)  # wants nothing
        target = await ctx.new_doc("UserGroup", {"group_name": "Спільна група"})
        for user in (ME, OTHER):
            await ctx.new_doc(
                "ToDo",
                {
                    "description": "x",
                    "reference_doctype": "UserGroup",
                    "reference_id": target["name"],
                    "assigned_to": user,
                    "status": "Open",
                },
            )
    assert await _follows(ctx) == [target["name"]]
    assert await _follows(ctx, OTHER) == []

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        shared = await ctx.new_doc("UserGroup", {"group_name": "Ще одна"})
        await ctx.new_doc(
            "SharedWith",
            {"reference_doctype": "UserGroup", "reference_id": shared["name"], "user": ME},
        )
    assert sorted(await _follows(ctx)) == sorted([target["name"], shared["name"]])


@pytest.mark.asyncio
async def test_auto_follow_created_and_commented(ctx):
    session = ctx.db._session()
    async with ctx.system_context(session, ctx.get_engine()):
        await _user(ctx, ME, follow_created=True, follow_commented=True)
        await _user(ctx, OTHER)
        theirs = await ctx.new_doc("UserGroup", {"group_name": "Чужа група"})
        await session.commit()

    async with ctx.context(session, ctx.get_engine(), _as(ME, admin=True)):
        await ctx.new_doc("UserGroup", {"group_name": "Моя група"})
        await ctx.new_doc(
            "Comment",
            {"reference_doctype": "UserGroup", "reference_id": theirs["name"], "content": "ok"},
        )
    async with ctx.context(session, ctx.get_engine(), _as(OTHER, admin=True)):
        await ctx.new_doc("UserGroup", {"group_name": "Ще група"})
    assert sorted(await _follows(ctx)) == sorted(["Моя група", "Чужа група"])
    assert await _follows(ctx, OTHER) == []


# Migration 0029


def test_migration_moves_unsubscribes_to_email_preferences():
    import importlib
    import json

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = importlib.import_module("grunt.db.migrations.versions.0029_notification_preference")
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_metadata_doc_type (name TEXT, table_name TEXT, definition JSON)"
            )
        )
        definition = {"name": "EmailUnsubscribe", "module": "email", "fields": []}
        conn.execute(
            sa.text("INSERT INTO grunt_metadata_doc_type VALUES ('EmailUnsubscribe', NULL, :d)"),
            {"d": json.dumps(definition)},
        )
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_email_email_unsubscribe "
                "(name TEXT, email TEXT, notification TEXT)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO grunt_email_email_unsubscribe VALUES "
                "('a', 'me@x.com', NULL), ('b', 'me@x.com', 'Task assigned')"
            )
        )
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        tables = set(sa.inspect(conn).get_table_names())
        rows = conn.execute(
            sa.text(
                "SELECT name, notification, channel FROM grunt_notification_preference "
                "ORDER BY name"
            )
        ).all()
        stored = conn.execute(sa.text("SELECT name, table_name FROM grunt_metadata_doc_type")).all()
    assert "grunt_email_email_unsubscribe" not in tables
    assert [tuple(r) for r in rows] == [("a", None, "email"), ("b", "Task assigned", "email")]
    assert [tuple(r) for r in stored] == [
        ("NotificationPreference", "grunt_notification_preference")
    ]
