"""``adopts``: an app takes over DocTypes of an app it depends on, rows and table kept."""

import json

import pytest

from grunt.metadata.doctype import DocType
from grunt.testkit import write_app_manifest

OLD_TABLE = "grunt_oldapp_adopt_target"


@pytest.fixture
def bench(tmp_path, monkeypatch, engine):
    from grunt.site.manager import site_manager

    sites_dir = tmp_path / "sites"
    (sites_dir / "testsite").mkdir(parents=True)
    (sites_dir / "testsite" / "grunt.site").write_text(
        json.dumps({"installed_apps": ["oldapp", "newapp"]})
    )
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", sites_dir)
    monkeypatch.setattr(site_manager, "get_engine", lambda site_name: engine)
    write_app_manifest(tmp_path / "apps" / "oldapp", {"name": "oldapp"})

    def new_app(*, table_name: str | None, **manifest):
        app_dir = tmp_path / "apps" / "newapp"
        write_app_manifest(app_dir, {"name": "newapp"}, **manifest)
        dt_dir = app_dir / "newapp" / "doctypes" / "AdoptTarget"
        dt_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "name": "AdoptTarget",
            "label": "Adopted",
            "module": "newapp",
            "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
        }
        if table_name:
            data["table_name"] = table_name
        (dt_dir / "AdoptTarget.json").write_text(json.dumps(data))

    return new_app


async def _owned_by_oldapp(db_session, engine):
    from grunt.metadata.registry import doctype_registry

    dt = DocType(
        name="AdoptTarget",
        label="Old",
        module="oldapp",
        app="oldapp",
        fields=[{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    )
    await doctype_registry.register(dt, db_session, engine)
    await db_session.commit()


async def _sync(db_session):
    from grunt.metadata.registry import doctype_registry
    from grunt.startup import app_install

    await app_install.register_installed_app_doctypes(db_session, "testsite")
    await db_session.commit()
    return doctype_registry._doctypes["AdoptTarget"]


@pytest.mark.asyncio
async def test_adopted_from_dependency_keeps_its_table(ctx, db_session, engine, bench):
    await _owned_by_oldapp(db_session, engine)
    await ctx.new_doc("AdoptTarget", {"title": "kept"})
    bench(table_name=OLD_TABLE, depends_on=["oldapp"], adopts=["AdoptTarget"])

    dt = await _sync(db_session)

    assert (dt.app, dt.module, dt.label) == ("newapp", "newapp", "Adopted")
    assert [r["title"] for r in await ctx.get_list("AdoptTarget", fields=["title"])] == ["kept"]


@pytest.mark.asyncio
async def test_not_adopted_without_dependency(ctx, db_session, engine, bench):
    await _owned_by_oldapp(db_session, engine)
    bench(table_name=OLD_TABLE, adopts=["AdoptTarget"])

    assert (await _sync(db_session)).app == "oldapp"


@pytest.mark.asyncio
async def test_not_adopted_when_table_would_change(ctx, db_session, engine, bench):
    await _owned_by_oldapp(db_session, engine)
    bench(table_name=None, depends_on=["oldapp"], adopts=["AdoptTarget"])

    assert (await _sync(db_session)).app == "oldapp"
