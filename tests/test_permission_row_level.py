"""Integration tests: DocTypePermission.match actually restricts grunt.get_list/get_doc.

Regression for the gap where row-level `match` (documented as
"owner == user") was evaluated only by the standalone Report engine and the
opt-in grunt.has_permission() helper — the main read pipeline (grunt.get_doc,
grunt.get_list) ignored it entirely and returned every row to any user whose
role had read=True on the DocType.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

TICKET_DOCTYPE = {
    "name": "PermTestTicket",
    "label": "Perm Test Ticket",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
    ],
    "permissions": [
        {"role": "Employee", "read": True, "match": "owner == user"},
    ],
}


@pytest.fixture
async def setup_ticket_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**TICKET_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


def _employee(email: str) -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=["Employee"], is_superadmin=False)


@pytest.mark.asyncio
async def test_get_list_filters_rows_by_match(ctx, setup_ticket_doctype, db_session, engine):
    from grunt.app import grunt

    alice_id = (await ctx.new_doc("PermTestTicket", {"title": "Alice's ticket"}))["name"]
    bob_id = (await ctx.new_doc("PermTestTicket", {"title": "Bob's ticket"}))["name"]
    await ctx.set_value("PermTestTicket", alice_id, "owner", "alice@example.com")
    await ctx.set_value("PermTestTicket", bob_id, "owner", "bob@example.com")
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        result = await grunt.get_list("PermTestTicket")

    names = [row["name"] for row in result]
    assert names == [alice_id]
    assert result.meta["total"] == 1


@pytest.mark.asyncio
async def test_get_doc_denies_non_matching_row(ctx, setup_ticket_doctype, db_session, engine):
    from grunt.app import grunt

    alice_id = (await ctx.new_doc("PermTestTicket", {"title": "Alice's ticket"}))["name"]
    bob_id = (await ctx.new_doc("PermTestTicket", {"title": "Bob's ticket"}))["name"]
    await ctx.set_value("PermTestTicket", alice_id, "owner", "alice@example.com")
    await ctx.set_value("PermTestTicket", bob_id, "owner", "bob@example.com")
    await ctx.db._session().commit()

    async with grunt.context(db_session, engine, _employee("alice@example.com")):
        # Own record: allowed.
        own = await grunt.get_doc("PermTestTicket", alice_id)
        assert own["name"] == alice_id

        # Someone else's record: denied, even though the role has read=True
        # on the DocType overall.
        with pytest.raises(HTTPException) as exc_info:
            await grunt.get_doc("PermTestTicket", bob_id)
        assert exc_info.value.status_code == 403
