"""Integration: ``Document.get_field_years`` — the options of a year quick filter
are the years actually present in the field, under the list's read permissions."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

LEDGER = {
    "name": "FYLedger",
    "label": "FY Ledger",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "signed_on", "label": "Signed on", "fieldtype": "Date"},
    ],
    "permissions": [
        {"role": "Reader", "read": True},
    ],
}


@pytest.fixture
async def setup_ledger(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LEDGER, "__is_new": True})
    for title, on in [
        ("a", "2021-03-01"),
        ("b", "2022-01-01"),
        ("c", "2022-12-31"),
        ("d", "2205-05-05"),
        ("e", None),
    ]:
        await ctx.new_doc("FYLedger", {"title": title, "signed_on": on})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_years_present_in_data_newest_first(ctx, setup_ledger, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("r@example.com", roles=["Reader"])):
        assert await Document.get_field_years("FYLedger", "signed_on") == [2205, 2022, 2021]


@pytest.mark.asyncio
async def test_non_date_field_has_no_years(ctx, setup_ledger, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("r@example.com", roles=["Reader"])):
        assert await Document.get_field_years("FYLedger", "title") == []
        assert await Document.get_field_years("FYLedger", "missing") == []


@pytest.mark.asyncio
async def test_no_read_permission_is_denied(ctx, setup_ledger, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("x@example.com", roles=[])):
        with pytest.raises(HTTPException) as e:
            await Document.get_field_years("FYLedger", "signed_on")
        assert e.value.status_code == 403
