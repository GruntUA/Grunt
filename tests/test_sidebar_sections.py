"""Document sidebar: app sections from the ``sidebar_sections`` hook and the
``perms`` that tell the desk which add buttons to show."""

from __future__ import annotations

import pytest

from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext
from grunt.document import sidebar
from tests.support import make_user

NOTE = {
    "name": "SideNote",
    "label": "Side Note",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Reader", "read": True},
        {"role": "Editor", "read": True, "write": True},
    ],
}


async def totals(doctype, doc_id, doc):
    return [
        {"label": "Title", "value": doc.get("title"), "indicator": "green", "junk": 1},
        {"label": "Open", "value": "list", "link": f"/app/{doctype}"},
    ]


def empty(doctype, doc_id, doc):
    return None


async def broken(doctype, doc_id, doc):
    raise RuntimeError("boom")


@pytest.fixture
async def note(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**NOTE, "__is_new": True})
    doc = await ctx.new_doc("SideNote", {"title": "Budget"})
    await ctx.db._session().commit()
    return doc


@pytest.fixture
def sections():
    saved = dict(sidebar._SECTIONS)
    sidebar._SECTIONS.clear()
    HOOK_CONSUMERS["sidebar_sections"].apply(
        [
            {"name": "totals", "label": "Totals", "method": f"{__name__}.totals"},
            {"name": "empty", "method": f"{__name__}.empty", "doctypes": ["SideNote"]},
            {"name": "broken", "method": f"{__name__}.broken"},
            {"name": "other", "method": f"{__name__}.totals", "doctypes": ["Elsewhere"]},
            {"name": "admins", "method": f"{__name__}.totals", "roles": ["System Manager"]},
        ],
        LoadContext(app_name="testapp", app_dir=None, fastapi_app=None),  # type: ignore[arg-type]
    )
    yield
    sidebar._SECTIONS.clear()
    sidebar._SECTIONS.update(saved)


async def _sidebar(db_session, engine, doc_id, roles):
    import grunt
    from grunt.document.base import Document

    async with grunt.context(db_session, engine, make_user("ann@example.com", roles=roles)):
        return await Document.get_sidebar(doctype="SideNote", doc_id=doc_id)


@pytest.mark.asyncio
async def test_app_sections(note, sections, db_session, engine):
    out = await _sidebar(db_session, engine, note["name"], ["Reader"])
    # empty -> hidden, broken -> skipped, other doctype / missing role -> not asked.
    assert out["sections"] == [
        {
            "name": "totals",
            "label": "Totals",
            "rows": [
                {"label": "Title", "value": "Budget", "indicator": "green"},
                {"label": "Open", "value": "list", "link": "/app/SideNote"},
            ],
        }
    ]
    admin = await _sidebar(db_session, engine, note["name"], ["System Manager"])
    assert [s["name"] for s in admin["sections"]] == ["totals", "admins"]


@pytest.mark.asyncio
async def test_perms(note, db_session, engine):
    reader = await _sidebar(db_session, engine, note["name"], ["Reader"])
    assert reader["perms"] == {"assign": True, "share": False, "tag": True}
    editor = await _sidebar(db_session, engine, note["name"], ["Editor"])
    assert editor["perms"]["share"] is True
