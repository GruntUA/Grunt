"""Attach / Image may keep a link to a file elsewhere, as is, without downloading it."""

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio

LINK = "https://backend.hromada.gov.ua/storage/uploads/files/%D0%90%20b.pdf?time=1743588653"

DT = {
    "name": "AlDoc",
    "label": "Al Doc",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "in_list_view": True},
        {"fieldname": "doc_file", "label": "File", "fieldtype": "Attach", "in_list_view": True},
        {"fieldname": "photo", "label": "Photo", "fieldtype": "Image"},
    ],
}


@pytest.fixture
async def al_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**DT, "__is_new": True})
    await ctx.db._session().commit()


async def test_link_is_stored_as_is_and_listed_by_name(ctx, al_doctype):
    doc = await ctx.new_doc(
        "AlDoc", {"title": "x", "doc_file": LINK, "photo": "https://x.test/a.png"}
    )
    assert doc["doc_file"] == LINK
    rows = await ctx.get_list("AlDoc", fields=["name", "doc_file"])
    assert rows[0]["doc_file__label"] == "А b.pdf"


async def test_stored_file_url_still_accepted(ctx, al_doctype):
    url = "/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id=abc123"
    doc = await ctx.new_doc("AlDoc", {"title": "x", "doc_file": url})
    assert doc["doc_file"] == url


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "//evil.test/a.pdf",
        "ftp://x.test/a.pdf",
        "data:text/html,hi",
        "a.pdf",
    ],
)
async def test_other_values_are_refused(ctx, al_doctype, value):
    with pytest.raises(HTTPException) as exc:
        await ctx.new_doc("AlDoc", {"title": "x", "doc_file": value})
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException):
        await ctx.new_doc("AlDoc", {"title": "x", "photo": value})
