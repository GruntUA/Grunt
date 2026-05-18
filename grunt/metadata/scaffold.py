"""DocType file scaffold — generates boilerplate files for new DocTypes.

When a DocType is created or updated via the API, this module writes
the colocated file structure to disk::

    {app}/{module}/doctypes/{Name}/
        {Name}.json   — DocType metadata (always overwritten)
        {Name}.py     — Python controller with auto-generated types
        {Name}.js     — Client script (only if missing)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from grunt.site.manager import site_manager

if TYPE_CHECKING:
    from pathlib import Path

    from grunt.metadata.doctype import DocType

logger = structlog.get_logger()

_SKIP_FIELDNAMES = frozenset({"name", "docstatus", "idx", "owner", "creation", "modified", "modified_by"})


def _build_scaffold_context(doctype_name: str, fields: list) -> dict:
    """Build Jinja template context for a new DocType controller."""
    from grunt.metadata.field import get_python_type, is_physical_fieldtype  # noqa: PLC0415

    physical_fields = []
    table_fields = []

    for field in fields:
        if hasattr(field, "fieldname"):
            fieldname = field.fieldname
            fieldtype = field.fieldtype
            label = field.label or ""
            options = getattr(field, "options", None)
        else:
            fieldname = field.get("fieldname", "")
            fieldtype = field.get("fieldtype", "Data")
            label = field.get("label", "")
            options = field.get("options")

        if fieldname in _SKIP_FIELDNAMES:
            continue

        if fieldtype in ("Table", "Table MultiSelect"):
            table_fields.append({"fieldname": fieldname, "options": options})
        elif is_physical_fieldtype(fieldtype):
            physical_fields.append({
                "fieldname": fieldname,
                "py_type": get_python_type(fieldtype),
                "label": label,
            })

    return {
        "name": doctype_name,
        "physical_fields": physical_fields,
        "table_fields": table_fields,
    }


# ── Helpers ──────────────────────────────────────────────────────────────


def _find_app_dir(module: str, app_name: str | None = None) -> Path | None:
    """Find the app directory that owns a given module name.

    If *app_name* is given, we look for ``bench_dir/apps/{app_name}`` directly.

    Otherwise scans all app directories for:
    1. apps/{app}/{module}  — module-based structure (Frappe style)
    2. apps/{app}           — flat structure where app == module
    """
    apps_dir = site_manager.bench_dir / "apps"

    # Fast path: app name known
    if app_name:
        if apps_dir.is_dir():
            candidate = apps_dir / app_name
            if candidate.is_dir():
                return candidate
        return None

    # Fallback: scan all app directories
    if apps_dir.is_dir():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir() or app_dir.name.startswith((".", "_")):
                continue
            if (app_dir / module).is_dir():
                return app_dir
            if app_dir.name == module:
                return app_dir

    return None


def export_doctype_files(dt: DocType, app_name: str | None = None) -> str | None:
    """Write DocType metadata and scaffold files to disk.

    Creates ``{app}/{doctype_dir}/`` with:
    - ``{Name}.json`` — always overwritten with current metadata
    - ``{Name}.py``  — controller with auto-generated type hints
    - ``{Name}.js``  — client script (only if missing)

    Supports two directory structures:
    - apps/{app}/{module}/doctypes/{Name}/   (module-based)
    - apps/{app}/doctypes/{Name}/            (flat app structure)

    *app_name* — when provided, used to locate the app directory directly
    instead of scanning for a matching module subdirectory.  Pass this when
    the module directory may not yet exist on disk (e.g. freshly created).

    Returns the absolute path to the written JSON file, or ``None`` if export
    was skipped (module directory not found).
    """
    from grunt.utils.codegen import render_template, sync_controller_types  # noqa: PLC0415

    app_dir = _find_app_dir(dt.module, app_name=app_name)
    if not app_dir:
        logger.warning(
            "scaffold.export_skip",
            doctype=dt.name,
            reason=f"module '{dt.module}' not found in apps",
        )
        return None

    # Determine path based on app structure.
    # If the module directory already exists, use module-based layout.
    # If not but app_name was provided, create the module directory now.
    module_dir = app_dir / dt.module
    if module_dir.is_dir():
        dt_dir = module_dir / "doctypes" / dt.name
    elif app_name:
        # Module dir doesn't exist yet — create it (new module)
        module_dir.mkdir(parents=True, exist_ok=True)
        dt_dir = module_dir / "doctypes" / dt.name
    else:
        # Flat structure: apps/{app}/doctypes/
        dt_dir = app_dir / "doctypes" / dt.name

    dt_dir.mkdir(parents=True, exist_ok=True)

    # JSON — always overwrite with current state.
    # exclude_defaults=True keeps only non-default values so the file stays
    # readable and diffs are meaningful (no noise from False/0/"" defaults).
    json_file = dt_dir / f"{dt.name}.json"
    json_file.write_text(
        json.dumps(dt.model_dump(exclude_defaults=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Controller — create if missing, otherwise only sync the auto-generated type block
    py_file = dt_dir / f"{dt.name}.py"
    if py_file.exists():
        sync_controller_types(py_file, dt.name, [f.model_dump() for f in dt.fields])
    else:
        context = _build_scaffold_context(dt.name, dt.fields)
        py_file.write_text(
            render_template("doctype/controller.py.jinja", context),
            encoding="utf-8",
        )

    # Client script — only create if missing
    js_file = dt_dir / f"{dt.name}.js"
    if not js_file.exists():
        js_file.write_text(
            render_template("doctype/client_script.js.jinja", {"name": dt.name}),
            encoding="utf-8",
        )

    logger.info("scaffold.exported", doctype=dt.name, path=str(dt_dir))
    return str(json_file.resolve())
