"""Regression: sync_installed_apps() used to blindly overwrite an existing
DocType whenever the incoming JSON differed from what was already loaded,
with no check on which app actually owns that name. Two apps (or an app and
grunt core) defining a doctype with the same name would silently clobber
each other on every `grunt db migrate` — whichever synced last "won", with
no warning. Found via a real collision: cms's WebPage/WebsiteSettings share
a name with grunt core's own built-in WebPage/WebsiteSettings doctypes.
"""

from __future__ import annotations

import json

import pytest

from grunt.metadata.doctype import DocType


@pytest.mark.asyncio
async def test_app_doctype_name_collision_is_refused(
    ctx, db_session, engine, tmp_path, monkeypatch
):
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager
    from grunt.startup.app_install import sync_installed_apps

    # Simulate a pre-existing doctype owned by grunt core (or any other app).
    core_dt = DocType(
        name="CollisionTarget", label="Core Owned", module="test", app="grunt", fields=[]
    )
    await doctype_registry.register(core_dt, db_session, engine)
    await db_session.commit()

    # A different, external app that (unknowingly) defines the same name.
    app_dir = tmp_path / "apps" / "collidingapp"
    dt_dir = app_dir / "collidingapp" / "doctypes" / "CollisionTarget"
    dt_dir.mkdir(parents=True)
    (app_dir / "app.json").write_text(
        json.dumps({"name": "collidingapp", "modules": ["collidingapp"]}), encoding="utf-8"
    )
    (dt_dir / "CollisionTarget.json").write_text(
        json.dumps(
            {
                "name": "CollisionTarget",
                "label": "App Owned",
                "module": "collidingapp",
                "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
            }
        ),
        encoding="utf-8",
    )

    sites_dir = tmp_path / "sites"
    site_dir = sites_dir / "testsite"
    site_dir.mkdir(parents=True)
    (site_dir / "grunt.site").write_text(
        json.dumps({"installed_apps": ["collidingapp"]}), encoding="utf-8"
    )

    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", sites_dir)
    monkeypatch.setattr(site_manager, "get_engine", lambda site_name: engine)

    await sync_installed_apps(db_session, "testsite")
    await db_session.commit()

    # The original, core-owned definition must survive untouched — not
    # silently overwritten by the colliding app's version.
    stored = doctype_registry._doctypes["CollisionTarget"]
    assert stored.app == "grunt"
    assert stored.label == "Core Owned"
