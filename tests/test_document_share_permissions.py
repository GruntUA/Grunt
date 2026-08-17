"""Regression: DocumentShare.before_insert() (and the create_share() method
that normally calls it) used to create a guest-accessible public share link
to ANY document, regardless of whether the creator could read it themselves.

get_shared_document() (grunt/api/v1/share.py) intentionally skips permission
guards for the fetch itself -- the token IS the authorization for that
lookup. That only stays safe if *minting* the token required read access to
the target document in the first place, which it never did: neither
create_share() nor the DocumentShare controller checked anything before
persisting the row. Any authenticated user could pick an arbitrary
doctype_name/doc_id (including someone else's private document) and hand
the resulting token to anyone.

Fixed in DocumentShare.before_insert() with a plain grunt.get_doc() call on
the target -- reusing the same read_guard + row-level match enforcement
every other read path goes through, and applying regardless of whether the
row is created via create_share() or the generic docs CRUD directly.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

SECRET_DOCTYPE = {
    "name": "ShareTestSecret",
    "label": "Share Test Secret",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
    ],
    "permissions": [
        {
            "role": "Owner",
            "read": True,
            "write": True,
            "create": True,
            "match": "owner == user",
        },
    ],
}


@pytest.fixture
async def setup_secret_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**SECRET_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_cannot_share_a_document_you_cannot_read(
    ctx, setup_secret_doctype, db_session, engine
):
    from grunt.app import grunt

    secret_id = (await ctx.new_doc("ShareTestSecret", {"title": "top secret"}))["name"]
    await ctx.set_value("ShareTestSecret", secret_id, "owner", "owner@example.com")
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, make_user("attacker@example.com")):
        with pytest.raises(HTTPException) as exc_info:
            await grunt.new_doc(
                "DocumentShare",
                {
                    "doctype_name": "ShareTestSecret",
                    "doc_id": secret_id,
                    "is_active": True,
                },
            )
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_share_their_own_document(ctx, setup_secret_doctype, db_session, engine):
    from grunt.app import grunt

    secret_id = (await ctx.new_doc("ShareTestSecret", {"title": "my doc"}))["name"]
    await ctx.set_value("ShareTestSecret", secret_id, "owner", "owner@example.com")
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, make_user("owner@example.com", roles=["Owner"])):
        share = await grunt.new_doc(
            "DocumentShare",
            {
                "doctype_name": "ShareTestSecret",
                "doc_id": secret_id,
                "is_active": True,
            },
        )
    assert share["token"]
