"""DocType file scaffold - generates boilerplate files for new DocTypes.

When a DocType is created or updated via the API, this module writes
the colocated file structure to disk::

    {package}/{module}/doctypes/{Name}/
        {Name}.json - DocType metadata (always overwritten)
        {Name}.py - Python controller with auto-generated types
        {Name}.js - Client script (only if missing)
"""

import json
from pathlib import Path

from grunt import log
from grunt.document.base import SYS_FIELDS, is_shadowed_field
from grunt.metadata.field import DocField, get_python_type, has_trait, is_physical_fieldtype
from grunt.site.manager import site_manager
from grunt.utils.codegen import render_template, sync_controller_types
from grunt.utils.strings import to_snake_case
lazy from grunt.metadata.doctype import DocType
lazy from grunt.metadata.extensions import export_extensions, without_extensions


def _build_scaffold_context(doctype_name: str, fields: list[DocField]) -> dict:
    """Build Jinja template context for a new DocType controller.

    ``fields`` is always ``DocType.fields`` from its one caller below - always
    real ``DocField`` instances, never raw dicts (this used to also accept a
    dict per field with silently different defaulting/error behavior, but
    nothing ever called it that way).
    """
    physical_fields = []
    table_fields = []

    for field in fields:
        fieldname = field.fieldname
        fieldtype = field.fieldtype
        label = field.label or ""
        options = field.options

        # A field the controller hides (doc.user, doc.delete) is read via self.data.
        if fieldname in SYS_FIELDS or is_shadowed_field(fieldname):
            continue

        if has_trait(fieldtype, "table"):
            table_fields.append({"fieldname": fieldname, "options": options})
        elif is_physical_fieldtype(fieldtype):
            physical_fields.append(
                {
                    "fieldname": fieldname,
                    "py_type": get_python_type(fieldtype),
                    "label": label,
                    "fieldtype": fieldtype,
                }
            )

    return {
        "name": doctype_name,
        "physical_fields": physical_fields,
        "table_fields": table_fields,
    }


# Helpers

_GRUNT_ROOT = Path(__file__).parent.parent  # grunt/metadata/ -> grunt/


def _package_root(app_name: str) -> Path | None:
    """Python package of *app_name*: ``grunt/`` for the core, else ``apps/{app}/{app}/``."""
    if app_name == "grunt":
        return _GRUNT_ROOT
    root = site_manager.bench_dir / "apps" / app_name / app_name
    return root if root.is_dir() else None


def _doctypes_dir(root: Path, module: str) -> Path:
    """``doctypes/`` of *module* - the package's own when the module is the app itself."""
    return root / "doctypes" if module in ("", root.name) else root / module / "doctypes"


def _json_module(path: Path) -> str | None:
    """``module`` declared in a DocType JSON file (None if unreadable or absent)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("module")
    except OSError, ValueError:
        return None


def _find_doctype_dir(dt: DocType, app_name: str | None = None) -> Path | None:
    """Directory for *dt*'s files: where its JSON already lives, else its module's ``doctypes/``.

    Without *app_name* every app package is scanned for the module.
    """
    if app_name:
        roots = [_package_root(app_name)]
    else:
        apps_dir = site_manager.bench_dir / "apps"
        app_dirs = sorted(apps_dir.iterdir()) if apps_dir.is_dir() else []
        roots = [_package_root(d.name) for d in app_dirs if d.is_dir()]

    for root in filter(None, roots):
        for existing in root.glob(f"**/doctypes/{dt.name}/{dt.name}.json"):
            # A same-named DocType of another module is not ours - never overwrite it.
            if _json_module(existing) in (None, dt.module):
                return existing.parent

    for root in filter(None, roots):
        doctypes_dir = _doctypes_dir(root, dt.module)
        if app_name or doctypes_dir.parent.is_dir():
            return doctypes_dir / dt.name
    return None


def _controller_file(dt_dir: Path, name: str) -> Path:
    """Existing controller (``{snake}.py`` or ``{Name}.py``), else ``{Name}.py`` to create."""
    snake = dt_dir / f"{to_snake_case(name)}.py"
    return snake if snake.exists() else dt_dir / f"{name}.py"


def export_doctype_files(dt: DocType, app_name: str | None = None) -> str | None:
    """Write DocType metadata and scaffold files to disk.

    Creates ``{package}/{module}/doctypes/{Name}/`` (``{package}/doctypes/{Name}/``
    when the module is the app package itself) with:
    - ``{Name}.json`` - always overwritten with current metadata
    - ``{Name}.py`` - controller with auto-generated type hints
    - ``{Name}.js`` - client script (only if missing)

    An existing ``{Name}.json`` anywhere in the app package wins over the
    computed location, so a DocType is never duplicated in a second folder.

    *app_name* - when provided, used to locate the app package directly
    instead of scanning for a matching module subdirectory.  Pass this when
    the module directory may not yet exist on disk (e.g. freshly created).

    Returns the absolute path to the written JSON file, or ``None`` if export
    was skipped (module directory not found).

    Fields other apps add (``doctype_ext/``) and the attributes their
    properties change belong to their files, not to this DocType's own JSON or
    controller types: they are written to those apps' ``doctype_ext/`` instead.
    """
    export_extensions(dt)
    dt = without_extensions(dt)
    dt_dir = _find_doctype_dir(dt, app_name=app_name)
    if not dt_dir:
        log.warning(
            "scaffold.export_skip",
            doctype=dt.name,
            reason=f"module '{dt.module}' not found in apps",
        )
        return None

    dt_dir.mkdir(parents=True, exist_ok=True)

    # JSON - always overwrite with current state.
    # exclude_defaults=True keeps only non-default values so the file stays
    # readable and diffs are meaningful (no noise from False/0/"" defaults).
    json_file = dt_dir / f"{dt.name}.json"
    json_file.write_text(
        json.dumps(
            dt.model_dump(exclude_defaults=True, exclude={"permissions_base"}),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )

    # Controller - create if missing, otherwise only sync the auto-generated type block
    py_file = _controller_file(dt_dir, dt.name)
    if py_file.exists():
        sync_controller_types(py_file, dt.name, [f.model_dump() for f in dt.fields])
    else:
        context = _build_scaffold_context(dt.name, dt.fields)
        py_file.write_text(
            render_template("doctype/controller.py.jinja", context),
        )

    # Client script - only create if missing
    js_file = dt_dir / f"{dt.name}.js"
    if not js_file.exists():
        js_file.write_text(
            render_template("doctype/client_script.js.jinja", {"name": dt.name}),
        )

    log.info("scaffold.exported", doctype=dt.name, path=str(dt_dir))
    return str(json_file.resolve())
