"""Regression: `grunt migrate` repeated work.

- sync_installed_apps() re-registered every app's DocTypes from JSON right
  after register_installed_app_doctypes() had already done it;
- _inject_core() rewrote every core DocType row on each run, changed or not;
- a fixture insert hitting an IntegrityError rolled back the whole session,
  so everything done before it was lost and redone on the next migrate.
"""

import json

import pytest
from sqlalchemy.exc import IntegrityError

from grunt.metadata.doctype import DocType
from grunt.testkit import write_app_manifest

_FX = {
    "name": "NrConfig",
    "label": "Nr Config",
    "module": "core",
    "autoname": "field:code",
    "fields": [{"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True}],
}


@pytest.mark.asyncio
async def test_sync_installed_apps_skips_registered_doctypes(
    ctx, db_session, engine, tmp_path, monkeypatch
):
    from grunt.site.manager import site_manager
    from grunt.startup import app_install

    app_dir = tmp_path / "apps" / "nrapp"
    (app_dir / "nrapp").mkdir(parents=True)
    write_app_manifest(app_dir, {"name": "nrapp", "modules": ["nrapp"]})
    site_dir = tmp_path / "sites" / "testsite"
    site_dir.mkdir(parents=True)
    (site_dir / "grunt.site").write_text(json.dumps({"installed_apps": ["nrapp"]}))

    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", tmp_path / "sites")
    monkeypatch.setattr(site_manager, "get_engine", lambda site_name: engine)

    calls: list[str] = []

    async def _register(session, eng, app_dir, app_name, app_modules):
        calls.append(app_name)
        return set()

    monkeypatch.setattr(app_install, "_register_app_doctypes", _register)

    await app_install.sync_installed_apps(db_session, "testsite", doctypes_registered=True)
    assert calls == []

    await app_install.sync_installed_apps(db_session, "testsite")
    assert calls == ["nrapp"]


@pytest.mark.asyncio
async def test_inject_core_writes_only_when_changed(ctx, db_session, engine, monkeypatch):
    from grunt.metadata import store
    from grunt.metadata.registry import doctype_registry

    source = DocType(name="NrCore", label="Nr Core", module="test", fields=[])
    await doctype_registry.register(source, db_session, engine)
    await db_session.commit()

    writes: list[str] = []
    real_update = store.update_doctype

    async def _update(session, dt):
        writes.append(dt.name)
        await real_update(session, dt)

    monkeypatch.setattr(store, "update_doctype", _update)

    await doctype_registry._inject_core(source.model_copy(deep=True), db_session, sync_db=True)
    assert writes == []

    changed = source.model_copy(deep=True, update={"label": "Nr Core Renamed"})
    await doctype_registry._inject_core(changed, db_session, sync_db=True)
    assert writes == ["NrCore"]


@pytest.mark.asyncio
async def test_fixture_conflict_keeps_earlier_session_work(ctx, db_session, engine, monkeypatch):
    import grunt
    from grunt.api.v1.meta import save_doctype
    from grunt.startup.fixtures import _apply_doctype_fixture

    await save_doctype(doctype_data={**_FX, "__is_new": True})
    await db_session.commit()

    # Uncommitted work done earlier in the same session (as sync_installed_apps does).
    await ctx.new_doc("NrConfig", {"code": "before"})

    real_new_doc = grunt.new_doc

    async def _conflicting_new_doc(doctype, data):
        await real_new_doc(doctype, data)  # partial write, must be undone
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(grunt, "new_doc", _conflicting_new_doc)
    await _apply_doctype_fixture(
        "NrConfig", [{"name": "clash", "code": "clash"}], db_session, engine
    )
    await db_session.commit()

    assert await grunt.exists("NrConfig", {"name": "before"})
    assert not await grunt.exists("NrConfig", {"name": "clash"})
