"""Document sidebar: app sections from the ``sidebar_sections`` hook and the
``perms`` that tell the desk which add buttons to show."""

from typing import Any

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


def extra_props(doctype, doc_id, doc):
    return [{"label": "Budget", "value": 10, "mono": True}]


def custom_id(doctype, doc_id, doc):
    return [{"label": "No.", "value": f"#{doc_id}"}]


@pytest.fixture
def core_sections():
    import grunt.core_hooks

    saved = dict(sidebar._SECTIONS)
    sidebar._SECTIONS.clear()
    consumer = HOOK_CONSUMERS["sidebar_sections"]
    consumer.apply(
        grunt.core_hooks.sidebar_sections,
        LoadContext(app_name="grunt", app_dir=None, fastapi_app=None),  # type: ignore[arg-type]
    )
    yield lambda specs: consumer.apply(
        specs,
        LoadContext(app_name="testapp", app_dir=None, fastapi_app=None),  # type: ignore[arg-type]
    )
    sidebar._SECTIONS.clear()
    sidebar._SECTIONS.update(saved)


@pytest.mark.asyncio
async def test_core_properties(note, core_sections, db_session, engine):
    out = await _sidebar(db_session, engine, note["name"], ["Reader"])
    # SideNote has no status, workflow or web page - only the ID.
    assert out["properties"] == [{"label": "ID", "value": note["name"], "copy": True, "mono": True}]
    assert out["sections"] == []


@pytest.mark.asyncio
async def test_app_properties_ordered_and_override(note, core_sections, db_session, engine):
    core_sections(
        [
            {
                "name": "budget",
                "method": f"{__name__}.extra_props",
                "placement": "properties",
                "order": 5,
            },
            {
                "name": "id",
                "method": f"{__name__}.custom_id",
                "placement": "properties",
                "order": 10,
            },
        ]
    )
    out = await _sidebar(db_session, engine, note["name"], ["Reader"])
    assert out["properties"] == [
        {"label": "Budget", "value": 10, "mono": True},
        {"label": "No.", "value": f"#{note['name']}"},
    ]


@pytest.mark.asyncio
async def test_status_row(core_sections, ctx, db_session, engine):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(
        doctype_data={
            **NOTE,
            "name": "SideTask",
            "fields": [{"fieldname": "status", "label": "Status", "fieldtype": "Data"}],
            "status_field": "status",
            "status_indicators": [{"value": "Done", "color": "success", "label": "Finished"}],
            "__is_new": True,
        }
    )
    done = await ctx.new_doc("SideTask", {"status": "Done"})
    odd = await ctx.new_doc("SideTask", {"status": "Odd"})
    await ctx.db._session().commit()

    async def props(doc_id):
        import grunt
        from grunt.document.base import Document

        async with grunt.context(
            db_session, engine, make_user("ann@example.com", roles=["Reader"])
        ):
            return (await Document.get_sidebar(doctype="SideTask", doc_id=doc_id))["properties"]

    status = (await props(done["name"]))[0]
    assert (status["value"], status["indicator"]) == ("Finished", "success")
    assert (await props(odd["name"]))[0]["indicator"] == "default"


def test_bad_placement():
    with pytest.raises(ValueError):
        bad: Any = "top"
        sidebar.register_sidebar_section(
            sidebar.SidebarSection(name="x", label="x", method=empty, placement=bad)
        )
