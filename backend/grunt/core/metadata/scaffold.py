"""DocType file scaffold — generates boilerplate files for new DocTypes.

When a DocType is created or updated via the API, this module writes
the colocated file structure to disk::

    {app}/{module}/doctypes/{Name}/
        {Name}.json   — DocType metadata (always overwritten)
        {Name}.py     — Python controller (only if missing)
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

# ── Templates ────────────────────────────────────────────────────────────

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

from grunt.core.document.base import Document


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


def _find_app_dir(module: str) -> Path | None:
    """Find the app directory that owns a given module name."""
    apps_dir = site_manager.bench_dir / "apps"
    if not apps_dir.is_dir():
        return None
    for app_dir in apps_dir.iterdir():
        if not app_dir.is_dir() or app_dir.name.startswith((".", "_")):
            continue
        if (app_dir / module).is_dir():
            return app_dir
    return None


def export_doctype_files(dt: DocType) -> None:
    """Write DocType metadata and scaffold files to disk.

    Creates ``{app}/{module}/doctypes/{Name}/`` with:
    - ``{Name}.json`` — always overwritten with current metadata
    - ``{Name}.py``  — controller stub (only if file doesn't exist)
    - ``{Name}.js``  — client script stub (only if file doesn't exist)
    """
    if dt.is_system:
        return

    app_dir = _find_app_dir(dt.module)
    if not app_dir:
        logger.warning("scaffold.export_skip", doctype=dt.name, reason=f"module '{dt.module}' not found in apps")
        return

    dt_dir = app_dir / dt.module / "doctypes" / dt.name
    dt_dir.mkdir(parents=True, exist_ok=True)

    # JSON — always overwrite with current state
    json_file = dt_dir / f"{dt.name}.json"
    json_file.write_text(
        json.dumps(dt.model_dump(exclude_none=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Controller — only create if missing
    py_file = dt_dir / f"{dt.name}.py"
    if not py_file.exists():
        py_file.write_text(CONTROLLER_TEMPLATE.format(name=dt.name), encoding="utf-8")

    # Client script — only create if missing
    js_file = dt_dir / f"{dt.name}.js"
    if not js_file.exists():
        js_file.write_text(CLIENT_SCRIPT_TEMPLATE.format(name=dt.name), encoding="utf-8")

    logger.info("scaffold.exported", doctype=dt.name, path=str(dt_dir))
