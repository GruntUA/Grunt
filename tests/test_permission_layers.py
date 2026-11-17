"""The site layer over an app's access rules (PERMISSIONS_PLAN step 6e): rules
the site changed survive ``grunt migrate``, the app's new rules still arrive as
the base (flagged for review), and the app's rules can be put back."""

import json

import pytest

from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocPermission
from grunt.metadata.permission_layers import customized, take_json_rules
from grunt.testkit import write_app_manifest

READ = {"role": "All", "actions": ["read"]}
WRITE = {"role": "All", "actions": ["read", "write"]}
SITE = {"role": "System Manager", "actions": ["read", "write", "delete"]}


def _rules(*rows: dict) -> list[DocPermission]:
    return [DocPermission.model_validate(r) for r in rows]


def _stored(permissions: list[dict], base: list[dict] | None, outdated: bool = False) -> DocType:
    return DocType(
        name="LayerBox",
        label="Layer Box",
        module="core",
        permissions=_rules(*permissions),
        permissions_base=None if base is None else _rules(*base),
        permissions_outdated=outdated,
    )


def _dump(rules: list[DocPermission]) -> list[dict]:
    return [r.model_dump() for r in rules]


def test_take_json_rules():
    json_rules = _rules(WRITE)
    # New DocType - the JSON's.
    got = take_json_rules(None, json_rules)
    assert _dump(got.permissions) == _dump(json_rules) and not got.permissions_outdated
    # Never changed on the site - follows the JSON.
    got = take_json_rules(_stored([READ], [READ]), json_rules)
    assert _dump(got.permissions) == _dump(json_rules) and not got.kept_site_rules
    # Changed on the site, JSON unchanged - kept, not outdated.
    got = take_json_rules(_stored([READ, SITE], [WRITE]), json_rules)
    assert _dump(got.permissions) == _dump(_rules(READ, SITE))
    assert _dump(got.permissions_base) == _dump(json_rules) and not got.permissions_outdated
    # Changed on the site and the JSON moved - kept, outdated.
    got = take_json_rules(_stored([READ, SITE], [READ]), json_rules)
    assert got.kept_site_rules and got.permissions_outdated
    # Unknown origin (no base) equal to the JSON - follows it; different - kept.
    assert not take_json_rules(_stored([WRITE], None), json_rules).kept_site_rules
    assert take_json_rules(_stored([READ], None), json_rules).kept_site_rules


@pytest.fixture
def bench(tmp_path, monkeypatch, engine):
    from grunt.site.manager import site_manager

    sites_dir = tmp_path / "sites"
    (sites_dir / "testsite").mkdir(parents=True)
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", sites_dir)
    monkeypatch.setattr(site_manager, "get_engine", lambda site_name: engine)
    app = tmp_path / "apps" / "layerapp"
    write_app_manifest(app, {"name": "layerapp"})
    dt_dir = app / "layerapp" / "doctypes" / "LayerBox"
    dt_dir.mkdir(parents=True)
    (sites_dir / "testsite" / "grunt.site").write_text(json.dumps({"installed_apps": ["layerapp"]}))

    def release(*permissions: dict):
        """The app's JSON as of a new release - returns its path."""
        path = dt_dir / "LayerBox.json"
        path.write_text(
            json.dumps(
                {
                    "name": "LayerBox",
                    "label": "Layer Box",
                    "module": "layerapp",
                    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
                    "permissions": list(permissions),
                }
            )
        )
        return path

    return release


async def _migrate(db_session):
    from grunt.startup import app_install

    await app_install.register_installed_app_doctypes(db_session, "testsite")
    await db_session.commit()


async def _stored_rules(db_session) -> DocType:
    from grunt.metadata import store

    return DocType.model_validate(await store.get_definition(db_session, "LayerBox"))


@pytest.mark.asyncio
async def test_site_rules_survive_migrate_and_can_be_restored(
    ctx, db_session, engine, bench, monkeypatch
):
    from grunt.api.v1.permission_layers import app_rules_diff, restore_app_rules
    from grunt.config import settings
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.warnings import doctype_warnings

    monkeypatch.setattr(settings, "debug", False)  # a production site: no app files written

    bench(READ, SITE)
    await _migrate(db_session)

    # The admin narrows the rules on the site (System Manager only).
    await ctx.save_doc("DocType", "LayerBox", {"permissions": [SITE]})
    await db_session.commit()
    dt = await _stored_rules(db_session)
    assert customized(dt) and not dt.permissions_outdated

    # Same release migrated again - the site's rules stay.
    await _migrate(db_session)
    assert _dump((await _stored_rules(db_session)).permissions) == _dump(_rules(SITE))

    # A new release changes the app's rules - kept, base moves, flagged.
    bench(WRITE, SITE)
    await _migrate(db_session)
    dt = await _stored_rules(db_session)
    assert _dump(dt.permissions) == _dump(_rules(SITE))
    assert _dump(dt.permissions_base) == _dump(_rules(WRITE, SITE))
    assert dt.permissions_outdated
    meta = await doctype_registry.get_meta("LayerBox")
    assert "permissions_outdated" in [w["code"] for w in await doctype_warnings(meta)]

    diff = await app_rules_diff("LayerBox")
    assert diff["customized"] and diff["outdated"]
    assert diff["summary"] == "permissions: − All (actions=[read, write])"

    # Restore the app's rules: equal to the base, nothing to review.
    await restore_app_rules("LayerBox")
    await db_session.commit()
    dt = await _stored_rules(db_session)
    assert _dump(dt.permissions) == _dump(dt.permissions_base) and not dt.permissions_outdated
    assert not customized(dt)

    # Following the app again: the next release applies as is.
    bench(READ, SITE)
    await _migrate(db_session)
    assert _dump((await _stored_rules(db_session)).permissions) == _dump(_rules(READ, SITE))


@pytest.mark.asyncio
async def test_production_save_does_not_write_app_files(
    ctx, db_session, engine, bench, monkeypatch
):
    """Outside developer mode a desk save stays in the site's database - the
    app's checkout stays clean (``grunt update`` refuses a dirty one)."""
    from grunt.config import settings

    monkeypatch.setattr(settings, "debug", False)
    path = bench(READ)
    await _migrate(db_session)
    before = path.read_text()
    await ctx.save_doc("DocType", "LayerBox", {"permissions": [SITE]})
    await db_session.commit()
    assert path.read_text() == before
    assert _dump((await _stored_rules(db_session)).permissions) == _dump(_rules(SITE))


@pytest.mark.asyncio
async def test_developer_mode_save_writes_the_app_rules(ctx, db_session, engine, bench):
    """In developer mode the save goes into the app's JSON - the rules are the
    app's, not a site customisation."""
    path = bench(READ)
    await _migrate(db_session)
    await ctx.save_doc("DocType", "LayerBox", {"permissions": [SITE]})
    await db_session.commit()
    assert json.loads(path.read_text())["permissions"] == [SITE]
    assert not customized(await _stored_rules(db_session))
