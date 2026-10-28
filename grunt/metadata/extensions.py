"""DocType extensions - fields one app adds to a DocType of another app (or of the core).

An extension lives in the app that adds the fields, one file per DocType::

    <app>/<module>/doctype_ext/Asset.json
    {
      "fields": [
        {"fieldname": "cf_card", "label": "Картка ОЗ", "fieldtype": "Link",
         "options": "CrystalFinanceCard", "insert_after": "inventory_number"}
      ]
    }

The DocType that ``grunt migrate`` stores is its own JSON plus the extensions
of the site's installed apps, merged by :func:`apply_extensions` in the order
of ``installed_apps`` (dependencies first). Merged fields carry
``source_app``, so the base definition can be told apart from them:
:func:`without_extensions` gives what belongs in the base app's JSON file, and
uninstalling the extending app removes its fields.

A fieldname the DocType already has - its own or another extension's - is
refused (logged, skipped), like a DocType name owned by another app.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from grunt import log
from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField
lazy from grunt.apps.manifest import is_app, read_manifest

EXT_DIR = "doctype_ext"


@dataclass(frozen=True, slots=True)
class DoctypeExtension:
    app: str
    doctype: str
    fields: tuple[dict[str, Any], ...]


def app_extensions(app_dir: Path, app_name: str) -> list[DoctypeExtension]:
    """The extensions an app ships in its modules' ``doctype_ext/`` dirs."""
    found: list[DoctypeExtension] = []
    for module in read_manifest(app_dir)["modules"]:
        for path in sorted((app_dir / module / EXT_DIR).glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError) as e:
                log.error("doctype_ext.unreadable", app=app_name, file=str(path), error=str(e))
                continue
            fields = tuple(f for f in data.get("fields", []) if isinstance(f, dict))
            found.append(DoctypeExtension(app_name, path.stem, fields))
    return found


def site_extensions(apps_dir: Path, installed_apps: list[str]) -> dict[str, list[DoctypeExtension]]:
    """DocType name -> extensions of the installed apps, in ``installed_apps`` order."""
    by_doctype: dict[str, list[DoctypeExtension]] = {}
    for app_name in installed_apps:
        app_dir = apps_dir / app_name
        if app_name == "grunt" or not is_app(app_dir):
            continue
        for ext in app_extensions(app_dir, app_name):
            by_doctype.setdefault(ext.doctype, []).append(ext)
    return by_doctype


def extensions_for_site(site_name: str | None) -> dict[str, list[DoctypeExtension]]:
    """:func:`site_extensions` of the site's ``grunt.site`` (empty without a site)."""
    from grunt.apps.required import with_dependencies
    from grunt.site.manager import site_manager

    if not site_name:
        return {}
    site_file = site_manager.sites_dir / site_name / "grunt.site"
    if not site_file.exists():
        return {}
    apps_dir = site_manager.bench_dir / "apps"
    installed = json.loads(site_file.read_text()).get("installed_apps", [])
    return site_extensions(apps_dir, with_dependencies(apps_dir, installed))


def apply_extensions(dt: DocType, extensions: list[DoctypeExtension] | None) -> DocType:
    """A copy of *dt* with the extensions' fields merged in (*dt* itself when none).

    A field goes right after its ``insert_after`` field (which may be one an
    earlier extension added), else at the end.
    """
    if not extensions:
        return dt
    merged = dt.model_copy(deep=True)
    owners = {f.fieldname: f.source_app or dt.app or "" for f in merged.fields}
    for ext in extensions:
        for spec in ext.fields:
            fieldname = spec.get("fieldname", "")
            if fieldname in owners:
                log.error(
                    "doctype_ext.field_collision",
                    doctype=dt.name,
                    field=fieldname,
                    app=ext.app,
                    owned_by=owners[fieldname],
                )
                continue
            try:
                field = DocField(**{**spec, "source_app": ext.app})
            except ValidationError as e:
                log.error(
                    "doctype_ext.field_invalid",
                    doctype=dt.name,
                    field=fieldname,
                    app=ext.app,
                    error=str(e),
                )
                continue
            merged.fields.insert(_position(merged, field, ext.app), field)
            owners[fieldname] = ext.app
    return merged


def _position(dt: DocType, field: DocField, app: str) -> int:
    if not field.insert_after:
        return len(dt.fields)
    for i, existing in enumerate(dt.fields):
        if existing.fieldname == field.insert_after:
            return i + 1
    log.warning(
        "doctype_ext.anchor_missing",
        doctype=dt.name,
        field=field.fieldname,
        insert_after=field.insert_after,
        app=app,
    )
    return len(dt.fields)


def without_extensions(dt: DocType) -> DocType:
    """*dt* without the fields other apps added - what its own app's JSON holds."""
    if not any(_foreign(dt, f) for f in dt.fields):
        return dt
    base = dt.model_copy(deep=True)
    base.fields = [f for f in base.fields if not _foreign(dt, f)]
    return base


def _foreign(dt: DocType, field: DocField) -> bool:
    return bool(field.source_app) and field.source_app != dt.app
