"""SharedWith grants: sharing one document gives a user, a role or everyone
access to it — and nothing more (not other documents, not create/delete), at
no higher a level than the sharer's, until its end date."""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from tests.support import make_user

BOX = {
    "name": "ShareBox",
    "label": "Share Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete", "share"]},
        {"role": "Editor", "actions": ["read", "write", "share"]},
        {"role": "Writer", "actions": ["read", "write"]},
    ],
}

BOB = "bob@example.com"


@pytest.fixture
async def boxes(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    for email in (BOB, "eve@example.com"):
        await ctx.new_doc("User", {"email": email, "first_name": "U", "last_name": "Ser"})
    a = (await ctx.new_doc("ShareBox", {"title": "A"}))["name"]
    b = (await ctx.new_doc("ShareBox", {"title": "B"}))["name"]
    await ctx.db._session().commit()
    return a, b


async def _share(
    ctx, doc: str, permission: str = "Read", user: str | None = BOB, **extra: object
) -> str:
    row = await ctx.new_doc(
        "SharedWith",
        {
            "reference_doctype": "ShareBox",
            "reference_id": doc,
            "user": user,
            "permission": permission,
            **extra,
        },
    )
    await ctx.db._session().commit()
    return row["name"]


def _bob():
    return make_user(BOB, roles=[])


@pytest.mark.asyncio
async def test_no_share_no_access(ctx, boxes, db_session, engine):
    import grunt

    a, _ = boxes
    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises(HTTPException) as exc:
            await grunt.get_doc("ShareBox", a)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_read_share_grants_that_document_only(ctx, boxes, db_session, engine):
    import grunt

    a, b = boxes
    await _share(ctx, a, "Read")

    async with grunt.context(db_session, engine, _bob()):
        assert (await grunt.get_doc("ShareBox", a))["title"] == "A"
        assert [r["name"] for r in await grunt.get_list("ShareBox")] == [a]
        with pytest.raises(HTTPException):
            await grunt.get_doc("ShareBox", b)
        with pytest.raises(HTTPException):
            await grunt.save_doc("ShareBox", a, {"title": "A2"})


@pytest.mark.asyncio
async def test_write_share_allows_edit_but_not_delete_or_other_docs(ctx, boxes, db_session, engine):
    import grunt

    a, b = boxes
    await _share(ctx, a, "Write")

    async with grunt.context(db_session, engine, _bob()):
        assert (await grunt.save_doc("ShareBox", a, {"title": "A2"}))["title"] == "A2"
        with pytest.raises(HTTPException):
            await grunt.save_doc("ShareBox", b, {"title": "B2"})
        with pytest.raises(HTTPException):
            await grunt.delete_doc("ShareBox", a)


@pytest.mark.asyncio
async def test_unshare_revokes_access(ctx, boxes, db_session, engine):
    import grunt

    a, _ = boxes
    share = await _share(ctx, a, "Read")
    await ctx.delete_doc("SharedWith", share)
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises(HTTPException):
            await grunt.get_doc("ShareBox", a)
        # No role and no share left → the DocType itself is off-limits again.
        with pytest.raises(HTTPException):
            await grunt.get_list("ShareBox")


@pytest.mark.asyncio
async def test_only_who_may_share_and_write_can_share(ctx, boxes, db_session, engine):
    import grunt
    from grunt.errors import ApplicationError

    a, _ = boxes
    await _share(ctx, a, "Read")  # bob can read A, not write it

    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.new_doc(
                "SharedWith",
                {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
            )

    # Write without the share permission isn't enough either.
    writer = make_user("wr@example.com", roles=["Writer"])
    async with grunt.context(db_session, engine, writer):
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.new_doc(
                "SharedWith",
                {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
            )

    editor = make_user("ed@example.com", roles=["Editor"])
    async with grunt.context(db_session, engine, editor):
        row = await grunt.new_doc(
            "SharedWith",
            {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
        )
    assert row["permission"] == "Read"


@pytest.mark.asyncio
async def test_share_to_unknown_user_rejected(ctx, boxes):
    from grunt.errors import ApplicationError

    a, _ = boxes
    with pytest.raises((ApplicationError, HTTPException)):
        await _share(ctx, a, "Read", user="ghost@example.com")


@pytest.mark.asyncio
async def test_share_rows_visible_to_whoever_reads_the_document(ctx, boxes, db_session, engine):
    import grunt

    a, _ = boxes
    editor = make_user("ed@example.com", roles=["Editor"])
    async with grunt.context(db_session, engine, editor):
        await grunt.new_doc(
            "SharedWith", {"reference_doctype": "ShareBox", "reference_id": a, "user": BOB}
        )
    await db_session.commit()

    for who, expected in ((editor, 1), (_bob(), 1), (make_user("eve@example.com"), 0)):
        async with grunt.context(db_session, engine, who):
            try:
                rows = await grunt.get_list("SharedWith")
            except HTTPException:
                rows = []
        assert len(rows) == expected, who.email


async def _titles(db_session, engine, who) -> list[str]:
    import grunt

    async with grunt.context(db_session, engine, who):
        try:
            return sorted(r["title"] for r in await grunt.get_list("ShareBox", fields=["title"]))
        except HTTPException:
            return []


@pytest.mark.asyncio
async def test_role_share_reaches_role_holders_only(ctx, boxes, db_session, engine):
    a, _ = boxes
    await ctx.new_doc("Role", {"role_name": "Clerk"})
    await _share(ctx, a, user=None, role="Clerk")

    assert await _titles(db_session, engine, make_user("cl@example.com", roles=["Clerk"])) == ["A"]
    assert await _titles(db_session, engine, _bob()) == []


@pytest.mark.asyncio
async def test_role_share_ignores_the_role_scope(ctx, boxes, db_session, engine):
    """A scope narrows the role's rules; a share is a choice of the document itself."""
    a, _ = boxes
    await ctx.new_doc("Role", {"role_name": "Clerk"})
    await _share(ctx, a, user=None, role="Clerk")
    scoped = make_user(
        "cl@example.com",
        roles=[{"role_name": "Clerk", "scope_doctype": "User", "scope_value": BOB}],
    )
    assert await _titles(db_session, engine, scoped) == ["A"]


@pytest.mark.asyncio
async def test_everyone_share_reaches_every_user(ctx, boxes, db_session, engine):
    a, _ = boxes
    await _share(ctx, a, user=None, everyone=True)
    assert await _titles(db_session, engine, _bob()) == ["A"]
    assert await _titles(db_session, engine, make_user("eve@example.com")) == ["A"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"user": None},
        {"user": BOB, "everyone": True},
        {"user": None, "role": "Clerk", "everyone": True},
    ],
)
async def test_share_needs_exactly_one_recipient(ctx, boxes, fields):
    from grunt.errors import ApplicationError

    a, _ = boxes
    await ctx.new_doc("Role", {"role_name": "Clerk"})
    with pytest.raises((ApplicationError, HTTPException)):
        await _share(ctx, a, **fields)


@pytest.mark.asyncio
async def test_share_ends_after_valid_to(ctx, boxes, db_session, engine):
    from sqlalchemy import update

    from grunt.metadata.registry import doctype_registry

    a, _ = boxes
    today = date.today()
    share = await _share(ctx, a, valid_to=today.isoformat())
    assert await _titles(db_session, engine, _bob()) == ["A"]  # inclusive

    # A past end date can't be set - move the stored one back as time would.
    table = (await doctype_registry.get_meta("SharedWith")).table
    await db_session.execute(
        update(table).where(table.c.name == share).values(valid_to=today - timedelta(days=1))
    )
    await db_session.commit()
    assert await _titles(db_session, engine, _bob()) == []


@pytest.mark.asyncio
async def test_past_end_date_rejected(ctx, boxes):
    from grunt.errors import ApplicationError

    a, _ = boxes
    with pytest.raises((ApplicationError, HTTPException)):
        await _share(ctx, a, valid_to=(date.today() - timedelta(days=1)).isoformat())


@pytest.mark.asyncio
async def test_reshare_passes_on_at_most_own_level(ctx, boxes, db_session, engine):
    import grunt
    from grunt.errors import ApplicationError

    a, b = boxes
    await _share(ctx, a, "Read", can_reshare=True)

    async with grunt.context(db_session, engine, _bob()):
        # Read + can share: may pass Read on - not Write, not another document.
        row = await grunt.new_doc(
            "SharedWith",
            {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
        )
        assert row["permission"] == "Read"
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.new_doc(
                "SharedWith",
                {
                    "reference_doctype": "ShareBox",
                    "reference_id": a,
                    "role": "System Manager",
                    "permission": "Write",
                },
            )
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.new_doc(
                "SharedWith",
                {"reference_doctype": "ShareBox", "reference_id": b, "user": "eve@example.com"},
            )
    await db_session.commit()
    assert await _titles(db_session, engine, make_user("eve@example.com")) == ["A"]


@pytest.mark.asyncio
async def test_share_without_reshare_cannot_be_passed_on(ctx, boxes, db_session, engine):
    import grunt
    from grunt.errors import ApplicationError

    a, _ = boxes
    await _share(ctx, a, "Write")
    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.new_doc(
                "SharedWith",
                {"reference_doctype": "ShareBox", "reference_id": a, "user": "eve@example.com"},
            )


@pytest.mark.asyncio
async def test_recipient_may_drop_own_share(ctx, boxes, db_session, engine):
    import grunt
    from grunt.errors import ApplicationError

    a, _ = boxes
    mine = await _share(ctx, a)
    theirs = await _share(ctx, a, user="eve@example.com")
    async with grunt.context(db_session, engine, _bob()):
        with pytest.raises((ApplicationError, HTTPException)):
            await grunt.delete_doc("SharedWith", theirs)
        await grunt.delete_doc("SharedWith", mine)
    await db_session.commit()
    assert await _titles(db_session, engine, _bob()) == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("standard_notifications")
async def test_share_notifies_the_user_and_role_holders(ctx, boxes):
    a, b = boxes
    await ctx.new_doc("Role", {"role_name": "Clerk"})
    await ctx.new_doc(
        "User",
        {
            "email": "cl@example.com",
            "first_name": "C",
            "last_name": "L",
            "roles": [{"role_name": "Clerk"}],
        },
    )
    await ctx.db._session().commit()
    await _share(ctx, a)
    await _share(ctx, b, user=None, role="Clerk")
    await _share(ctx, b, user=None, everyone=True)

    async def bell(user: str) -> list[str]:
        rows = await ctx.db.get_all(
            "NotificationLog", filters={"user": user}, fields=["doc_id"], limit=10
        )
        return sorted(r["doc_id"] for r in rows)

    assert await bell(BOB) == [a]
    assert await bell("cl@example.com") == [b]
    assert await bell("eve@example.com") == []  # "everyone" tells nobody
