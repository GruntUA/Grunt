"""Regression: mark_as_read()/unsubscribe_push() used to act on ANY
notification/push-subscription by id/endpoint alone, with no check that it
belonged to the calling user — any authenticated user could mark someone
else's notification as read, or unsubscribe someone else's push endpoint.
"""

from __future__ import annotations

import pytest

from tests.support import make_user


@pytest.mark.asyncio
async def test_mark_as_read_ignores_other_users_notification(ctx):
    from grunt.api.v1.notifications import mark_as_read

    owner = make_user("owner@grunt.example.com")
    attacker = make_user("attacker@grunt.example.com")

    async with ctx.system_context(ctx.db._session()):
        notif = await ctx.new_doc(
            "Notification",
            {
                "user": owner.email,
                "doctype": "Order",
                "doc_id": "ORD-1",
                "subject": "Test",
                "message": "Test",
                "is_read": False,
            },
        )
        await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine(), attacker):
        updated = await mark_as_read(notif["name"])
    assert updated is False

    async with ctx.system_context(ctx.db._session()):
        still_unread = await ctx.get_doc("Notification", notif["name"])
    assert still_unread["is_read"] is False


@pytest.mark.asyncio
async def test_mark_as_read_updates_own_notification(ctx):
    from grunt.api.v1.notifications import mark_as_read

    owner = make_user("owner2@grunt.example.com")

    async with ctx.system_context(ctx.db._session()):
        notif = await ctx.new_doc(
            "Notification",
            {
                "user": owner.email,
                "doctype": "Order",
                "doc_id": "ORD-2",
                "subject": "Test",
                "message": "Test",
                "is_read": False,
            },
        )
        await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine(), owner):
        updated = await mark_as_read(notif["name"])
    assert updated is True

    async with ctx.system_context(ctx.db._session()):
        now_read = await ctx.get_doc("Notification", notif["name"])
    assert now_read["is_read"] is True


@pytest.mark.asyncio
async def test_unsubscribe_push_ignores_other_users_subscription(ctx):
    from grunt.api.v1.notifications import unsubscribe_push

    owner = make_user("push-owner@grunt.example.com")
    attacker = make_user("push-attacker@grunt.example.com")

    async with ctx.system_context(ctx.db._session()):
        await ctx.new_doc(
            "PushSubscription",
            {
                "user": owner.email,
                "endpoint": "https://push.example.com/abc123",
                "p256dh": "key",
                "auth": "auth",
            },
        )
        await ctx.db._session().commit()

    async with ctx.context(ctx.db._session(), ctx._require_engine(), attacker):
        await unsubscribe_push("https://push.example.com/abc123")

    async with ctx.system_context(ctx.db._session()):
        remaining = await ctx.get_list(
            "PushSubscription", filters={"endpoint": "https://push.example.com/abc123"}
        )
    assert len(remaining) == 1
