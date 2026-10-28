"""DocType extensions - fields one app adds to a DocType of another app (or of the core).

An extension lives in the app that adds the fields, one file per DocType::

    <app>/<module>/doctype_ext/Asset.json
    {
      "fields": [
        {"fieldname": "cf_card", "label": "Картка ОЗ", "fieldtype": "Link",
         "options": "CrystalFinanceCard", "insert_after": "inventory_number"}
      ],
      "properties": {"inventory_number": {"required": true}}
    }

The DocType that ``grunt migrate`` stores is its own JSON plus the extensions
of the site's installed apps, merged by :func:`apply_extensions` in the order
of ``installed_apps`` (dependencies first). Merged fields carry
``source_app``, so the base definition can be told apart from them:
:func:`without_extensions` gives what belongs in the base app's JSON file, and
uninstalling the extending app removes its fields.

``properties`` change attributes of fields the DocType already has; the
field keeps the values they replaced in ``ext_base`` (per app), so the base
JSON is exported with its own values and the change is undone with the app.

A fieldname the DocType already has - its own or another extension's - is
refused (logged, skipped), like a DocType name owned by another app; so is an
attribute another extension already changes, and a change of ``fieldname`` /
``fieldtype``.

In developer mode, saving the DocType (Studio) writes the fields and
properties back to the files of the apps they belong to (:func:`export_extensions`).
"""

import json
from dataclasses import dataclass
from dataclasses import field as dc_field
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
    properties: dict[str, dict[str, Any]] = dc_field(default_factory=dict)


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
            props = {k: v for k, v in (data.get("properties") or {}).items() if isinstance(v, dict)}
            found.append(DoctypeExtension(app_name, path.stem, fields, props))
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
    """A copy of *dt* with the extensions' fields and properties merged in
    (*dt* itself when none).

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
    for ext in extensions:
        for fieldname, attrs in ext.properties.items():
            _apply_properties(merged, fieldname, attrs, ext.app)
    return merged


# Attributes ``properties`` may not change: what a field is, and the extension bookkeeping.
_FIXED = frozenset({"fieldname", "fieldtype", "source_app", "insert_after", "ext_base"})


def _apply_properties(dt: DocType, fieldname: str, attrs: dict[str, Any], app: str) -> None:
    index = next((i for i, f in enumerate(dt.fields) if f.fieldname == fieldname), None)
    if index is None:
        log.warning("doctype_ext.property_field_missing", doctype=dt.name, field=fieldname, app=app)
        return
    field = dt.fields[index]
    for attr, value in attrs.items():
        owner = next((a for a, vals in (field.ext_base or {}).items() if attr in vals), None)
        if attr in _FIXED or attr not in DocField.model_fields or (owner and owner != app):
            log.error(
                "doctype_ext.property_refused",
                doctype=dt.name,
                field=fieldname,
                attribute=attr,
                app=app,
                changed_by=owner,
            )
            continue
        ext_base = {a: dict(v) for a, v in (field.ext_base or {}).items()}
        ext_base.setdefault(app, {}).setdefault(attr, getattr(field, attr))
        try:
            field = DocField(**{**field.model_dump(), attr: value, "ext_base": ext_base})
        except ValidationError as e:
            log.error(
                "doctype_ext.property_invalid",
                doctype=dt.name,
                field=fieldname,
                attribute=attr,
                app=app,
                error=str(e),
            )
            continue
        dt.fields[index] = field


def revert_properties(field: DocField, app: str | None = None) -> DocField:
    """*field* with the values *app*'s properties replaced (all apps' when None) back."""
    if not field.ext_base:
        return field
    restore: dict[str, Any] = {}
    rest = {}
    for owner, vals in field.ext_base.items():
        if app is None or owner == app:
            restore.update(vals)
        else:
            rest[owner] = vals
    if not restore:
        return field
    return field.model_copy(update={**restore, "ext_base": rest or None})


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
    """*dt* without what other apps added (fields) or changed (properties) - what
    its own app's JSON holds."""
    if not any(_foreign(dt, f) or f.ext_base for f in dt.fields):
        return dt
    base = dt.model_copy(deep=True)
    base.fields = [revert_properties(f) for f in base.fields if not _foreign(dt, f)]
    return base


def _foreign(dt: DocType, field: DocField) -> bool:
    return bool(field.source_app) and field.source_app != dt.app


def export_extensions(dt: DocType) -> list[Path]:
    """Write the fields and properties other apps have in *dt* into their
    ``doctype_ext/<DocType>.json`` (Studio's "Customize": mark a field with the
    app it belongs to and save). Returns the files written or removed.

    A field goes after the field it follows in *dt* now. The file of an app
    installed on the site that has nothing left in *dt* is removed - otherwise
    ``grunt migrate`` would bring back what was deleted in Studio.
    """
    from grunt.site.manager import site_manager

    fields: dict[str, list[dict[str, Any]]] = {}
    props: dict[str, dict[str, dict[str, Any]]] = {}
    previous: str | None = None
    for f in dt.fields:
        if _foreign(dt, f) and f.source_app:
            spec = f.model_dump(
                mode="json",
                exclude_defaults=True,
                exclude={"source_app", "ext_base", "insert_after"},
            )
            if previous:
                spec["insert_after"] = previous
            fields.setdefault(f.source_app, []).append(spec)
        for app, vals in (f.ext_base or {}).items():
            if app != dt.app:
                current = f.model_dump(mode="json", include=set(vals))
                props.setdefault(app, {})[f.fieldname] = current
        previous = f.fieldname

    apps_dir = site_manager.bench_dir / "apps"
    try:
        installed = site_manager.get_installed_apps(site_manager.get_active_site())
    except Exception:  # noqa: BLE001 - no site (tests, scripts): only write, never remove
        installed = []
    changed: list[Path] = []
    for app in sorted({*fields, *props, *(a for a in installed if a != dt.app)}):
        app_dir = apps_dir / app
        if app == "grunt" or not is_app(app_dir):
            continue
        path = _ext_file(app_dir, dt.name)
        data: dict[str, Any] = {}
        if fields.get(app):
            data["fields"] = fields[app]
        if props.get(app):
            data["properties"] = props[app]
        if not data:
            if path.exists():
                path.unlink()
                changed.append(path)
            continue
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if not path.exists() or path.read_text() != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            changed.append(path)
    for path in changed:
        log.info("doctype_ext.exported", doctype=dt.name, path=str(path))
    return changed


def _ext_file(app_dir: Path, doctype: str) -> Path:
    """The app's extension file for *doctype*: an existing one, else in its first module."""
    modules = read_manifest(app_dir)["modules"]
    for module in modules:
        path = app_dir / module / EXT_DIR / f"{doctype}.json"
        if path.exists():
            return path
    return app_dir / modules[0] / EXT_DIR / f"{doctype}.json"
