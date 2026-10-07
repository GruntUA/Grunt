"""Integration: ``Document.get_preview`` — the link hover card of a DocType with
``show_preview_popup`` (title, image, in_preview fields, read permissions)."""

from __future__ import annotations

import pytest

from tests.support import make_user

ASSET = {
    "name": "PVAsset",
    "label": "PV Asset",
    "module": "core",
    "title_field": "title",
    "show_preview_popup": True,
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data", "required": True},
        {"fieldname": "serial_no", "label": "Serial No", "fieldtype": "Data", "in_preview": True},
        {"fieldname": "status", "label": "Status", "fieldtype": "Data", "in_preview": True},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Data"},
    ],
    "permissions": [{"role": "Reader", "read": True}],
}

PLAIN = {
    "name": "PVPlain",
    "label": "PV Plain",
    "module": "core",
    "show_preview_popup": True,
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Data"},
    ],
    "permissions": [{"role": "Reader", "read": True}],
}


@pytest.fixture
async def setup_preview(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ASSET, "__is_new": True})
    await save_doctype(doctype_data={**PLAIN, "__is_new": True})
    await save_doctype(
        doctype_data={
            **PLAIN,
            "name": "PVOff",
            "label": "PV Off",
            "show_preview_popup": False,
            "__is_new": True,
        }
    )
    asset = await ctx.new_doc("PVAsset", {"title": "Generator", "serial_no": "BH1", "notes": "x"})
    plain = await ctx.new_doc("PVPlain", {"code": "C-1", "notes": "y"})
    off = await ctx.new_doc("PVOff", {"code": "C-2"})
    await ctx.db._session().commit()
    return {"asset": asset["name"], "plain": plain["name"], "off": off["name"]}


@pytest.mark.asyncio
async def test_preview_has_title_and_in_preview_fields(ctx, setup_preview, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("r@example.com", roles=["Reader"])):
        data = await Document.get_preview("PVAsset", setup_preview["asset"])

    assert data["title"] == "Generator"
    assert [f["fieldname"] for f in data["fields"]] == ["serial_no", "status"]
    assert data["row"]["serial_no"] == "BH1"
    assert "notes" not in data["row"]


@pytest.mark.asyncio
async def test_preview_falls_back_to_required_fields(ctx, setup_preview, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("r@example.com", roles=["Reader"])):
        data = await Document.get_preview("PVPlain", setup_preview["plain"])

    assert [f["fieldname"] for f in data["fields"]] == ["code"]
    assert data["row"]["code"] == "C-1"


@pytest.mark.asyncio
async def test_preview_off_or_unreadable_is_none(ctx, setup_preview, db_session, engine):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("r@example.com", roles=["Reader"])):
        assert await Document.get_preview("PVOff", setup_preview["off"]) is None
        assert await Document.get_preview("PVAsset", "missing") is None

    async with grunt.context(db_session, engine, make_user("n@example.com", roles=["Nobody"])):
        assert await Document.get_preview("PVAsset", setup_preview["asset"]) is None
