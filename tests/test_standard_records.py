"""Standard records - documents that ship with an app as JSON files.

In developer mode a ``standard_records`` DocType's record marked
``is_standard`` is written to ``<app>/<module>/records/<doctype>/<record>/``;
``apply_records`` (run by migrate) reads the folders back into the database.
"""

from __future__ import annotations

import json

import pytest

_PARENT = {
    "name": "SrConfig",
    "label": "Sr Config",
    "module": "core",
    "autoname": "field:code",
    "standard_records": True,
    "title_field": "title",
    "fields": [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "body", "label": "Body", "fieldtype": "Code", "options": "html"},
        {"fieldname": "rows", "label": "Rows", "fieldtype": "Table", "options": "SrConfigRow"},
    ],
}

_CHILD = {
    "name": "SrConfigRow",
    "label": "Sr Config Row",
    "module": "core",
    "is_child": True,
    "fields": [{"fieldname": "label", "label": "Label", "fieldtype": "Data"}],
}


@pytest.fixture
async def sr_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**_CHILD, "__is_new": True})
    await save_doctype(doctype_data={**_PARENT, "__is_new": True})
    if await ctx.db.exists("GruntInstalledApp", "demo") is None:
        await ctx.new_doc("GruntInstalledApp", {"name": "demo", "title": "Demo"})
    await ctx.db._session().commit()


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    """A bench with one app ``demo`` (module ``demo``), in developer mode."""
    from grunt.config import settings
    from grunt.site.manager import site_manager

    module = tmp_path / "apps" / "demo" / "demo"
    module.mkdir(parents=True)
    (tmp_path / "apps" / "demo" / "app.json").write_text(json.dumps({"modules": ["demo"]}))
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "get_all_installed_apps", lambda: {"demo"})
    monkeypatch.setattr(settings, "debug", True)
    return module / "records" / "sr_config"


async def _save(ctx, **values):
    from grunt.standard_records import sync_files

    name = values["code"]
    if await ctx.find_doc("SrConfig", name) is None:
        doc = await ctx.new_doc("SrConfig", values)
    else:
        doc = await ctx.save_doc("SrConfig", name, values)
    await sync_files("after_save", doctype="SrConfig", doc=doc)
    await ctx.db._session().commit()
    return doc


def test_flag_adds_standard_fields():
    from grunt.metadata.doctype import DocType

    dt = DocType.model_validate({**_PARENT, "name": "SrOther"})
    fields = {f.fieldname: f for f in dt.fields}
    assert fields["is_standard"].fieldtype == "Check"
    assert fields["app"].options == "GruntInstalledApp"


def test_core_hooks_mirror_records():
    from grunt.core_hooks import doc_events

    hook = "grunt.standard_records.sync_files"
    for event in ("after_save", "after_delete", "after_rename"):
        assert hook in doc_events["*"][event]


@pytest.mark.asyncio
async def test_save_writes_document_json_and_code_files(ctx, sr_doctype, demo_app):
    await _save(
        ctx,
        code="welcome",
        title="Welcome page",
        body="<h1>Hi</h1>",
        rows=[{"label": "a"}],
        is_standard=True,
        app="demo",
    )

    folder = demo_app / "welcome_page"
    data = json.loads((folder / "welcome_page.json").read_text(encoding="utf-8"))
    assert data == {
        "doctype": "SrConfig",
        "name": "welcome",
        "code": "welcome",
        "title": "Welcome page",
        "rows": [{"doctype": "SrConfigRow", "label": "a"}],
        "is_standard": True,
        "app": "demo",
    }
    assert (folder / "body.html").read_text(encoding="utf-8") == "<h1>Hi</h1>"


@pytest.mark.asyncio
async def test_unmarking_or_deleting_removes_the_folder(ctx, sr_doctype, demo_app):
    from grunt.standard_records import sync_files

    await _save(ctx, code="one", title="One", is_standard=True, app="demo")
    assert (demo_app / "one").is_dir()
    await _save(ctx, code="one", is_standard=False)
    assert not (demo_app / "one").exists()

    await _save(ctx, code="two", title="Two", is_standard=True, app="demo")
    doc = await ctx.get_doc("SrConfig", "two")
    await ctx.delete_doc("SrConfig", "two")
    await sync_files("after_delete", doctype="SrConfig", doc=doc)
    assert not (demo_app / "two").exists()


@pytest.mark.asyncio
async def test_no_files_outside_developer_mode(ctx, sr_doctype, demo_app, monkeypatch):
    from grunt.config import settings

    monkeypatch.setattr(settings, "debug", False)
    await _save(ctx, code="prod", title="Prod", is_standard=True, app="demo")
    assert not demo_app.exists()


@pytest.mark.asyncio
async def test_apply_records_inserts_and_updates_from_files(
    ctx, sr_doctype, demo_app, db_session, engine
):
    from grunt.standard_records import apply_records

    folder = demo_app / "shipped"
    folder.mkdir(parents=True)
    (folder / "shipped.json").write_text(
        json.dumps(
            {
                "doctype": "SrConfig",
                "name": "shipped",
                "code": "shipped",
                "title": "Shipped",
                "rows": [{"doctype": "SrConfigRow", "label": "r1"}],
            }
        ),
        encoding="utf-8",
    )
    (folder / "body.html").write_text("<p>v1</p>", encoding="utf-8")

    assert await apply_records("demo", db_session, engine) == 1
    await db_session.commit()
    doc = await ctx.get_doc("SrConfig", "shipped")
    assert (doc["title"], doc["body"], doc["is_standard"], doc["app"]) == (
        "Shipped",
        "<p>v1</p>",
        True,
        "demo",
    )
    assert [r["label"] for r in doc["rows"]] == ["r1"]

    (folder / "body.html").write_text("<p>v2</p>", encoding="utf-8")
    await apply_records("demo", db_session, engine)
    await db_session.commit()
    updated = await ctx.get_doc("SrConfig", "shipped")
    assert updated["body"] == "<p>v2</p>"

    await apply_records("demo", db_session, engine)
    await db_session.commit()
    unchanged = await ctx.get_doc("SrConfig", "shipped")
    assert unchanged["modified_at"] == updated["modified_at"]
