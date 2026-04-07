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
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from grunt.core.site.manager import site_manager

if TYPE_CHECKING:
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()


# ── Type mapping ────────────────────────────────────────────────────────────


FIELDTYPE_TO_PYTHON = {
    "Data": "str | None",
    "Text": "str | None",
    "LongText": "str | None",
    "Int": "int | None",
    "Float": "float | None",
    "Check": "bool | None",
    "Date": "str | None",
    "Datetime": "str | None",
    "Time": "str | None",
    "Link": "str | None",
    "MultiLink": "list[str] | None",
    "Attach": "str | None",
    "Image": "str | None",
    "Select": "str | None",
    "RichText": "str | None",
    "JSON": "dict | None",
    "Code": "str | None",
    "Color": "str | None",
    "Signature": "str | None",
    "Geolocation": "str | None",
    "HTMLEditor": "str | None",
    "BarCode": "str | None",
    "Rating": "int | None",
    "Percent": "float | None",
    "Duration": "float | None",
}


def _generate_type_block(doctype_name: str, fields: list) -> str:
    """Generate auto-typed field annotations from a DocType definition.

    Maps fieldtype to Python type hints.
    Fields can be either dicts or Pydantic DocField models.
    """
    # Collect field type annotations (skip structural fields)
    field_lines = []
    for field in fields:
        # Handle both dict and Pydantic model
        if hasattr(field, "fieldname"):
            fieldname = field.fieldname
            fieldtype = field.fieldtype
        else:
            fieldname = field.get("fieldname", "")
            fieldtype = field.get("fieldtype", "Data")

        # Skip structural fields
        if fieldtype in ("Section", "Column", "Tab", "Table", "Empty"):
            continue

        # Skip standard fields
        if fieldname in ("name", "docstatus", "idx", "owner", "creation", "modified", "modified_by"):
            continue

        py_type = FIELDTYPE_TO_PYTHON.get(fieldtype, "Any | None")
        field_lines.append(f"\t\t{fieldname}: {py_type}")

    # Build the type hints block
    type_block = f"""# begin: auto-generated types
# This code is auto-generated. Do not modify anything in this block.

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
\tfrom typing import DF

\tclass {doctype_name}:
\t\t\"\"\"Type hints for {doctype_name} fields.\"\"\"

{chr(10).join(field_lines) if field_lines else chr(9)*2 + 'name: str | None'}

# end: auto-generated types
"""

    return type_block


# ── Templates ────────────────────────────────────────────────────────────────

CONTROLLER_TEMPLATE = '''\
"""Controller for {name}.

Lifecycle hooks — override any method to add custom logic:
  before_insert  — before a NEW document is saved to DB
  after_insert   — after a NEW document is saved to DB
  validate       — runs before every save (insert or update), raise to block
  before_save    — before an EXISTING document is updated
  after_save     — after an EXISTING document is updated
  before_delete  — before document is deleted
  after_delete   — after document is deleted

Access fields:
  self.field_name          — read field value
  self.field_name = value  — set field value
  self.data                — full document dict
  self.doctype             — DocType name ("{name}")
  self.user                — current GruntUser (or None)
  self.session             — async SQLAlchemy session (for advanced queries)
"""

from __future__ import annotations

from grunt.core.document.base import Document

{type_hints}


class {name}(Document):

    async def validate(self) -> None:
        """Runs before every save — raise an exception to block."""
        pass

    async def before_save(self) -> None:
        """Runs before an existing document is updated."""
        pass

    async def after_save(self) -> None:
        """Runs after document is saved to the database."""
        pass
'''

CLIENT_SCRIPT_TEMPLATE = '''\
// Client script for {name}
//
// Available objects:
//   frm.doc                              — current document data (live, always up-to-date)
//   frm.doc.fieldname                    — read a field value
//   frm.is_new                           — true if document is not yet saved
//   frm.fields                           — list of field definitions
//
// Form helpers:
//   frm.get_value(fieldname)             — read a field value
//   frm.set_value(fieldname, value)      — set a field value
//   frm.toggle_display(fieldname, show)  — show/hide a field (true = visible)
//   frm.toggle_reqd(fieldname, reqd)     — make field required/optional
//   frm.set_df_property(field, prop, v)  — set any field property
//   frm.add_button(label, action, opts)  — add a custom button to the form
//   frm.save()                           — save the document
//
// Framework helpers:
//   grunt.call({{ method, args }})         — call a server script (POST /api/v1/method/...)
//   grunt.msgprint(msg)                  — show info dialog
//   grunt.msgprint({{ message, title }})   — show dialog with title
//   grunt.show_alert(msg, type)          — show toast (type: success/error/info/warning)
//   grunt.confirm(msg)                   — show confirm dialog (returns Promise<boolean>)
//   grunt.throw(msg)                     — throw an error and stop execution

function on_load(frm) {{
  // Called once when the form loads — add buttons, set initial state
}}

function on_change(frm, fieldname) {{
  // Called when any field value changes
}}

function validate(frm) {{
  // Called before save — return false to cancel
  return true
}}
'''


# ── Helpers ──────────────────────────────────────────────────────────────


def _find_app_dir(module: str, app_name: str | None = None) -> Path | None:
    """Find the app directory that owns a given module name.

    If *app_name* is given, we look for ``apps/{app_name}`` directly (no
    directory-existence check needed — the module dir may not exist yet).

    Otherwise tries multiple patterns:
    1. apps/{app}/{module}          — module-based structure (Frappe style)
    2. apps/{app}                   — flat structure where app == module
    3. grunt_apps/{app}/{module}    — relative grunt_apps (dev)
    4. grunt_apps/{app}             — flat relative grunt_apps
    """
    apps_dir = site_manager.bench_dir / "apps"

    # Fast path: app name known — go directly, no scanning
    if app_name:
        if apps_dir.is_dir():
            candidate = apps_dir / app_name
            if candidate.is_dir():
                return candidate
        grunt_apps_dir = Path("grunt_apps")
        if grunt_apps_dir.is_dir():
            candidate = grunt_apps_dir / app_name
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

    grunt_apps_dir = Path("grunt_apps")
    if grunt_apps_dir.is_dir():
        for app_dir in grunt_apps_dir.iterdir():
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
    was skipped (system DocType or module directory not found).
    """
    if dt.is_system:
        return None

    app_dir = _find_app_dir(dt.module, app_name=app_name)
    if not app_dir:
        logger.warning("scaffold.export_skip", doctype=dt.name, reason=f"module '{dt.module}' not found in apps")
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

    # Generate type hints from fields
    type_hints = _generate_type_block(dt.name, dt.fields)

    # Controller — create or update with types
    py_file = dt_dir / f"{dt.name}.py"
    py_content = CONTROLLER_TEMPLATE.format(name=dt.name, type_hints=type_hints)
    py_file.write_text(py_content, encoding="utf-8")

    # Client script — only create if missing
    js_file = dt_dir / f"{dt.name}.js"
    if not js_file.exists():
        js_file.write_text(CLIENT_SCRIPT_TEMPLATE.format(name=dt.name), encoding="utf-8")

    logger.info("scaffold.exported", doctype=dt.name, path=str(dt_dir))
    return str(json_file.resolve())
