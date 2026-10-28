"""Fields one app adds to another app's DocType (``<module>/doctype_ext/<DocType>.json``)."""

import json

import pytest
from sqlalchemy import inspect

from grunt.metadata.doctype import DocType
from grunt.metadata.extensions import DoctypeExtension, apply_extensions, without_extensions
from grunt.metadata.field import DocField
from grunt.testkit import write_app_manifest

TITLE = {"fieldname": "title", "label": "Title", "fieldtype": "Data"}
CODE = {"fieldname": "code", "label": "Code", "fieldtype": "Data"}


def _dt(*fields, name="ExtTarget", app="extbase"):
    return DocType(
        name=name, label=name, module=app, app=app, fields=[DocField(**f) for f in fields]
    )


def _names(dt):
    return [f.fieldname for f in dt.fields]


def _ext(app, *fields, doctype="ExtTarget"):
    return DoctypeExtension(app, doctype, tuple(fields))


# Merge


def test_fields_go_after_their_anchor_and_carry_source_app():
    dt = _dt(TITLE, CODE)
    merged = apply_extensions(
        dt,
        [
            _ext("a", {"fieldname": "a_x", "fieldtype": "Data", "insert_after": "title"}),
            _ext("b", {"fieldname": "b_y", "fieldtype": "Data", "insert_after": "a_x"}),
            _ext("b", {"fieldname": "b_z", "fieldtype": "Data"}),
        ],
    )
    assert _names(merged) == ["title", "a_x", "b_y", "code", "b_z"]
    assert [f.source_app for f in merged.fields] == [None, "a", "b", None, "b"]
    assert _names(dt) == ["title", "code"]  # the input is not modified


def test_colliding_and_invalid_fields_are_skipped():
    merged = apply_extensions(
        _dt(TITLE),
        [
            _ext("a", {"fieldname": "title", "fieldtype": "Int"}),
            _ext("a", {"fieldname": "a_x", "fieldtype": "Data"}),
            _ext("b", {"fieldname": "a_x", "fieldtype": "Data"}),
            _ext("b", {"fieldname": "b_bad"}),  # no fieldtype
            _ext("b", {"fieldname": "b_lost", "fieldtype": "Data", "insert_after": "nope"}),
        ],
    )
    assert _names(merged) == ["title", "a_x", "b_lost"]
    assert merged.fields[0].fieldtype == "Data"
    assert merged.fields[1].source_app == "a"


def test_without_extensions_keeps_own_fields():
    merged = apply_extensions(_dt(TITLE), [_ext("a", {"fieldname": "a_x", "fieldtype": "Data"})])
    assert _names(without_extensions(merged)) == ["title"]


# grunt migrate: app DocTypes


@pytest.fixture
def bench(tmp_path, monkeypatch, engine):
    """A bench with an app owning ExtTarget and an app extending it."""
    from grunt.site.manager import site_manager

    sites_dir = tmp_path / "sites"
    (sites_dir / "testsite").mkdir(parents=True)
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    monkeypatch.setattr(site_manager, "sites_dir", sites_dir)
    monkeypatch.setattr(site_manager, "get_engine", lambda site_name: engine)

    apps = tmp_path / "apps"
    base = apps / "extbase"
    write_app_manifest(base, {"name": "extbase"})
    dt_dir = base / "extbase" / "doctypes" / "ExtTarget"
    dt_dir.mkdir(parents=True)
    (dt_dir / "ExtTarget.json").write_text(
        json.dumps({"name": "ExtTarget", "label": "Ext", "module": "extbase", "fields": [TITLE]})
    )

    addon = apps / "extaddon"
    write_app_manifest(addon, {"name": "extaddon"}, extends=["extbase"])
    (addon / "extaddon" / "doctype_ext").mkdir(parents=True)
    (addon / "extaddon" / "doctype_ext" / "ExtTarget.json").write_text(
        json.dumps(
            {
                "fields": [
                    {
                        "fieldname": "addon_ref",
                        "label": "Ref",
                        "fieldtype": "Data",
                        "insert_after": "title",
                    }
                ]
            }
        )
    )

    def install(*names):
        (sites_dir / "testsite" / "grunt.site").write_text(
            json.dumps({"installed_apps": list(names)})
        )

    return install


async def _migrate(db_session):
    from grunt.startup import app_install

    synced = await app_install.register_installed_app_doctypes(db_session, "testsite")
    await db_session.commit()
    return synced


@pytest.mark.asyncio
async def test_extension_fields_survive_migrate_without_flapping(ctx, db_session, engine, bench):
    from grunt.metadata.compiler import compile_doctype_to_table
    from grunt.metadata.registry import doctype_registry

    bench("extbase", "extaddon")

    assert await _migrate(db_session) == {"ExtTarget"}
    assert await _migrate(db_session) == set()  # nothing to re-sync on the next run

    dt = doctype_registry._doctypes["ExtTarget"]
    assert _names(dt) == ["title", "addon_ref"]
    assert dt.fields[1].source_app == "extaddon"
    table = compile_doctype_to_table(dt).name
    async with engine.connect() as conn:
        cols = await conn.run_sync(lambda c: [x["name"] for x in inspect(c).get_columns(table)])
    assert "addon_ref" in cols


@pytest.mark.asyncio
async def test_field_leaves_with_its_app(ctx, db_session, engine, bench):
    from grunt.metadata.registry import doctype_registry

    bench("extbase", "extaddon")
    await _migrate(db_session)
    bench("extbase")
    await _migrate(db_session)

    assert _names(doctype_registry._doctypes["ExtTarget"]) == ["title"]


# Core DocTypes keep Studio-added fields; extension fields follow their files


@pytest.mark.asyncio
async def test_core_doctype_extension_fields(ctx, db_session):
    from grunt.metadata import store
    from grunt.metadata.registry import doctype_registry

    core = _dt(TITLE, name="ExtCoreTarget", app="grunt")
    ext = _ext("extaddon", {"fieldname": "addon_ref", "fieldtype": "Data"}, doctype="ExtCoreTarget")

    await doctype_registry._inject_core(apply_extensions(core, [ext]), db_session, sync_db=True)
    stored = doctype_registry._doctypes["ExtCoreTarget"]
    stored.fields.append(DocField(fieldname="local_note", fieldtype="Data"))  # added in Studio
    await store.update_doctype(db_session, stored)

    relabeled = _ext(
        "extaddon",
        {"fieldname": "addon_ref", "label": "Renamed", "fieldtype": "Data"},
        doctype="ExtCoreTarget",
    )
    await doctype_registry._inject_core(
        apply_extensions(core, [relabeled]), db_session, sync_db=True
    )
    fields = {f.fieldname: f for f in doctype_registry._doctypes["ExtCoreTarget"].fields}
    assert fields["addon_ref"].label == "Renamed"

    await doctype_registry._inject_core(core, db_session, sync_db=True)
    assert _names(doctype_registry._doctypes["ExtCoreTarget"]) == ["title", "local_note"]


# Studio export


def test_export_leaves_extension_fields_out(tmp_path, monkeypatch):
    from grunt.metadata import scaffold

    monkeypatch.setattr(scaffold, "_find_doctype_dir", lambda dt, app_name=None: tmp_path)
    merged = apply_extensions(_dt(TITLE), [_ext("a", {"fieldname": "a_x", "fieldtype": "Data"})])

    scaffold.export_doctype_files(merged)

    saved = json.loads((tmp_path / "ExtTarget.json").read_text())
    assert [f["fieldname"] for f in saved["fields"]] == ["title"]


# Uninstall


@pytest.mark.asyncio
async def test_uninstall_strips_fields_and_drops_columns(ctx, db_session, engine, bench):
    from grunt.cli.app import _drop_extension_columns, _extension_fields, _strip_extension_fields
    from grunt.metadata.compiler import compile_doctype_to_table
    from grunt.metadata.registry import doctype_registry

    bench("extbase", "extaddon")
    await _migrate(db_session)
    dt = doctype_registry._doctypes["ExtTarget"]
    table = compile_doctype_to_table(dt).name

    ext_fields = _extension_fields("extaddon", await doctype_registry.list_all(), skip=set())
    assert [(d.name, [f.fieldname for f in fs]) for d, fs in ext_fields] == [
        ("ExtTarget", ["addon_ref"])
    ]
    await _strip_extension_fields(db_session, engine, ext_fields)
    await db_session.commit()
    await _drop_extension_columns(engine, ext_fields)

    assert _names(doctype_registry._doctypes["ExtTarget"]) == ["title"]
    async with engine.connect() as conn:
        cols = await conn.run_sync(lambda c: [x["name"] for x in inspect(c).get_columns(table)])
    assert "addon_ref" not in cols
    assert "title" in cols


@pytest.mark.asyncio
async def test_update_without_source_app_keeps_the_mark(ctx, db_session, engine, bench):
    from grunt.metadata.registry import doctype_registry

    bench("extbase", "extaddon")
    await _migrate(db_session)

    edited = doctype_registry._doctypes["ExtTarget"].model_copy(deep=True)
    for field in edited.fields:
        field.source_app = None  # an editor that doesn't know the attribute
    edited.label = "Edited"
    await doctype_registry.update(edited, db_session, engine)

    fields = {f.fieldname: f for f in doctype_registry._doctypes["ExtTarget"].fields}
    assert fields["addon_ref"].source_app == "extaddon"
    assert fields["title"].source_app is None
