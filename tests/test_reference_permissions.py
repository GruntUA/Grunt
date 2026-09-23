"""inherit_permission_from: comments / tags / attachments follow the read access
of the document they belong to."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

SECRET = {
    "name": "SecretCase",
    "label": "Secret Case",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Investigator", "read": True, "match": "owner == user"},
    ],
}


@pytest.fixture
async def cases(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SECRET, "__is_new": True})
    mine = (await ctx.new_doc("SecretCase", {"title": "Mine"}))["name"]
    other = (await ctx.new_doc("SecretCase", {"title": "Other"}))["name"]
    await ctx.set_value("SecretCase", mine, "owner", "ann@example.com")
    for case in (mine, other):
        await ctx.new_doc(
            "Comment",
            {"reference_doctype": "SecretCase", "reference_id": case, "content": f"on {case}"},
        )
    await ctx.new_doc("File", {"file_name": "lib.txt", "path": "lib.txt", "file_url": "/x"})
    await ctx.new_doc(
        "File",
        {
            "file_name": "evidence.txt",
            "path": "evidence.txt",
            "file_url": "/y",
            "attached_to_doctype": "SecretCase",
            "attached_to_id": other,
        },
    )
    await ctx.db._session().commit()
    return mine, other


def _ann():
    return make_user("ann@example.com", roles=["Investigator"])


@pytest.mark.asyncio
async def test_comment_list_shows_only_readable_documents(ctx, cases, db_session, engine):
    from grunt.app import grunt

    mine, _ = cases
    async with grunt.context(db_session, engine, _ann()):
        rows = await grunt.get_list("Comment", filters={"reference_doctype": "SecretCase"})
    assert [r["reference_id"] for r in rows] == [mine]


@pytest.mark.asyncio
async def test_comment_on_unreadable_document_is_forbidden(ctx, cases, db_session, engine):
    from grunt.app import grunt

    _, other = cases
    [row] = await ctx.db.get_all(
        "Comment", filters={"reference_id": other}, fields=["name"], limit=1
    )
    async with grunt.context(db_session, engine, _ann()):
        with pytest.raises(HTTPException) as exc:
            await grunt.get_doc("Comment", row["name"])
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            await grunt.new_doc(
                "Comment",
                {"reference_doctype": "SecretCase", "reference_id": other, "content": "hi"},
            )


@pytest.mark.asyncio
async def test_comment_on_readable_document_allowed(ctx, cases, db_session, engine):
    from grunt.app import grunt

    mine, _ = cases
    async with grunt.context(db_session, engine, _ann()):
        row = await grunt.new_doc(
            "Comment", {"reference_doctype": "SecretCase", "reference_id": mine, "content": "ok"}
        )
        assert (await grunt.get_doc("Comment", row["name"]))["content"] == "ok"


@pytest.mark.asyncio
async def test_unattached_files_keep_role_access(ctx, cases, db_session, engine):
    from grunt.app import grunt

    async with grunt.context(db_session, engine, _ann()):
        names = {r["file_name"] for r in await grunt.get_list("File", limit=100)}
    assert "lib.txt" in names
    assert "evidence.txt" not in names


@pytest.mark.asyncio
async def test_share_opens_the_comments_too(ctx, cases, db_session, engine):
    from grunt.app import grunt

    _, other = cases
    await ctx.new_doc("User", {"email": "ann@example.com", "first_name": "Ann", "last_name": "A"})
    await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "SecretCase", "reference_id": other, "user": "ann@example.com"},
    )
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _ann()):
        rows = await grunt.get_list("Comment", filters={"reference_doctype": "SecretCase"})
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_private_attachment_download_follows_document_access(ctx, cases, db_session, engine):
    from grunt.app import grunt
    from grunt.storage.doctypes.File.file import get_content

    mine, other = cases
    ids = {}
    for case in (mine, other):
        row = await ctx.new_doc(
            "File",
            {
                "file_name": f"{case}.txt",
                "path": f"missing/{case}.txt",
                "file_url": "/z",
                "is_public": False,
                "attached_to_doctype": "SecretCase",
                "attached_to_id": case,
            },
        )
        ids[case] = row["name"]
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _ann()):
        with pytest.raises(HTTPException) as denied:
            await get_content(ids[other])
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as allowed:
            await get_content(ids[mine])  # permitted — fails only on the fake storage path
        assert allowed.value.status_code == 404
