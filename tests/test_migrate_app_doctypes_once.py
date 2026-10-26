"""Regression: `grunt migrate` synced a changed app DocType's table twice -
first from the stale stored definition (the sync loop), then again when
sync_installed_apps() updated it from JSON. register_installed_app_doctypes()
now applies the JSON before the loop and reports what it already synced, and
a later sync_installed_apps() finds nothing left to update.
"""

import json

import pytest

from grunt.metadata.doctype import DocType
from grunt.testkit import write_app_manifest


@pytest.mark.asyncio
async def test_changed_app_doctype_synced_once(ctx, db_session, engine, tmp_path, monkeypatch):
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager
    from grunt.startup import app_install

    stored = DocType(name="OnceTarget", label="Old", module="onceapp", app="onceapp", fields=[])
    await doctype_registry.register(stored, db_session, engine)
    await db_session.commit()

    app_dir = tmp_path / "apps" / "onceapp"
    dt_dir = app_dir / "onceapp" / "doctypes" / "OnceTarget"
    dt_dir.mkdir(parents=True)
    write_app_manifest(app_dir, {"name": "onceapp", "modules": ["onceapp"]})
    (dt_dir / "OnceTarget.json").write_text(
        json.dumps(
            {
                "name": "OnceTarget",
                "label": "New",
                "module": "onceapp",
                "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
            }
        ),
    )

    sites_dir = tmp_path / "sites"
    site_dir = sites_dir / "testsite"
    site_dir.mkdir(parents=True)
    (site_dir / "grunt.site").write_text(json.dumps({"installed_apps": ["onceapp"]}))

    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", sites_dir)
    monkeypatch.setattr(site_manager, "get_engine", lambda site_name: engine)

    synced = await app_install.register_installed_app_doctypes(db_session, "testsite")
    await db_session.commit()

    assert synced == {"OnceTarget"}
    assert doctype_registry._doctypes["OnceTarget"].label == "New"

    # The JSON is applied now, so the fixtures pass has nothing to re-sync.
    assert (
        await app_install._register_app_doctypes(
            db_session, engine, app_dir, "onceapp", {"onceapp"}
        )
        == set()
    )
