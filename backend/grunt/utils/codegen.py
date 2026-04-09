"""Code generation utilities for Grunt.

Provides:
  - Template rendering via Jinja2 (with app-level override support)
  - Smart controller type-block sync (replaces only auto-generated section)
  - Fieldtype → Python type mapping helpers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from grunt.utils.strings import to_snake_case

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BEGIN_MARKER = "# begin: auto-generated types"
_END_MARKER = "# end: auto-generated types"

_FIELDTYPE_TO_PY: dict[str, str] = {
    "Data": "str | None",
    "Text": "str | None",
    "LongText": "str | None",
    "RichText": "str | None",
    "Code": "str | None",
    "Select": "str | None",
    "Link": "str | None",
    "Attach": "str | None",
    "Image": "str | None",
    "Color": "str | None",
    "Signature": "str | None",
    "Int": "int | None",
    "Float": "float | None",
    "Check": "bool",
    "Date": "datetime.date | None",
    "Datetime": "datetime.datetime | None",
    "Time": "datetime.time | None",
    "JSON": "dict | list | None",
    "Geolocation": "dict | None",
    "MultiLink": "list[str]",
    "Rating": "int | None",
    "Percent": "float | None",
    "Duration": "float | None",
}

_NON_PHYSICAL = {"Section", "Column", "Tab", "Empty"}
_SKIP_FIELDNAMES = {"name", "id", "docstatus", "owner", "created_at", "modified_at", "modified_by"}


# ---------------------------------------------------------------------------
# Template environment
# ---------------------------------------------------------------------------


def _build_env(extra_template_dirs: list[Path] | None = None) -> Environment:
    """Build a Jinja2 Environment searching framework templates + any app overrides.

    Search order (first match wins):
      1. Each path in *extra_template_dirs* (app-level overrides)
      2. grunt/templates/ (framework defaults)
    """
    framework_templates = Path(__file__).parent.parent / "templates"
    search_paths: list[str | Path] = [*(extra_template_dirs or []), framework_templates]

    return Environment(
        loader=FileSystemLoader([str(p) for p in search_paths]),
        autoescape=select_autoescape(enabled_extensions=()),  # no HTML escaping for code
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(
    template_name: str,
    context: dict[str, Any],
    extra_template_dirs: list[Path] | None = None,
) -> str:
    """Render a Jinja2 template by name.

    Args:
        template_name:        Relative path inside templates/, e.g. "doctype/controller.py.jinja"
        context:              Variables passed to the template.
        extra_template_dirs:  Additional directories to search first (app overrides).

    Returns:
        Rendered string content.
    """
    env = _build_env(extra_template_dirs)
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def build_controller_context(name: str, fields: list[dict]) -> dict[str, Any]:
    """Prepare the template context for doctype/controller.py.jinja."""
    physical = [
        f
        for f in fields
        if f.get("fieldtype") not in _NON_PHYSICAL and f.get("fieldname") not in _SKIP_FIELDNAMES
    ]

    needs_datetime = any(f["fieldtype"] in {"Date", "Datetime", "Time"} for f in physical)

    enriched = []
    for f in physical:
        enriched.append(
            {
                **f,
                "py_type": _FIELDTYPE_TO_PY.get(f["fieldtype"], "Any"),
            }
        )

    return {
        "name": name,
        "physical_fields": enriched,
        "needs_datetime": needs_datetime,
    }


# ---------------------------------------------------------------------------
# Smart controller sync
# ---------------------------------------------------------------------------


def _render_type_block(name: str, fields: list[dict]) -> str:
    """Render only the auto-generated types block (without surrounding class)."""
    physical = [
        f
        for f in fields
        if f.get("fieldtype") not in _NON_PHYSICAL
        and f.get("fieldtype") != "Table"
        and f.get("fieldname") not in _SKIP_FIELDNAMES
    ]
    table_fields = [
        f
        for f in fields
        if f.get("fieldtype") == "Table" and f.get("fieldname") not in _SKIP_FIELDNAMES
    ]

    indent = "    "
    indent2 = indent * 2

    field_lines: list[str] = []
    for f in physical:
        py_type = _FIELDTYPE_TO_PY.get(f["fieldtype"], "Any")
        comment = f"  # {f['label']}" if f.get("label") and f["label"] != f["fieldname"] else ""
        field_lines.append(f"{indent2}{f['fieldname']}: {py_type}{comment}")
    for f in table_fields:
        table_opt = f.get("options", "?")
        field_lines.append(f"{indent2}{f['fieldname']}: list[dict]  # Table: {table_opt}")

    needs_datetime = any(
        f["fieldtype"] in {"Date", "Datetime", "Time"}
        for f in fields
        if f.get("fieldtype") not in _NON_PHYSICAL and f.get("fieldname") not in _SKIP_FIELDNAMES
    )

    if field_lines:
        imports = "from typing import TYPE_CHECKING, Any"
        if needs_datetime:
            imports = f"import datetime\n{imports}"
        type_if = f"{indent}if TYPE_CHECKING:\n" + "\n".join(field_lines)
    else:
        imports = "from typing import Any"
        type_if = f"{indent}if TYPE_CHECKING:\n{indent2}pass"

    return (
        f"{_BEGIN_MARKER}\n"
        f"{indent}# This code is auto-generated. Do not modify anything in this block.\n"
        f"\n"
        f"{imports}\n"
        f"\n"
        f"\n"
        f"class {name}Controller:\n"
        f"{type_if}\n"
        f"{_END_MARKER}"
    )


def sync_controller_types(py_path: Path, name: str, fields: list[dict]) -> bool:
    """Update only the auto-generated types block inside an existing controller file.

    Replaces the region between *_BEGIN_MARKER* and *_END_MARKER*.
    If the markers are absent the block is inserted after the last top-level import.
    Custom code outside the markers is **never** touched.

    Returns True if the file was modified, False if already up-to-date.
    """
    source = py_path.read_text(encoding="utf-8")
    new_block = _render_type_block(name, fields)

    begin_idx = source.find(_BEGIN_MARKER)
    end_idx = source.find(_END_MARKER)

    if begin_idx != -1 and end_idx != -1:
        # Replace existing block
        end_of_block = end_idx + len(_END_MARKER)
        new_source = source[:begin_idx] + new_block + source[end_of_block:]
    else:
        # Insert after last import line
        lines = source.splitlines(keepends=True)
        insert_after = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(("import ", "from ")) or stripped.startswith("from __future__"):
                insert_after = i
        new_source = (
            "".join(lines[: insert_after + 1])
            + "\n"
            + new_block
            + "\n"
            + "".join(lines[insert_after + 1 :])
        )

    if new_source == source:
        return False

    py_path.write_text(new_source, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Test generation helpers
# ---------------------------------------------------------------------------

_FAKE_VALUES: dict[str, object] = {
    "Data": "Test Value",
    "Text": "Test text value",
    "LongText": "Long text content",
    "Int": 42,
    "Float": 3.14,
    "Check": True,
    "Date": "2026-01-15",
    "Datetime": "2026-01-15T10:00:00",
    "Time": "10:00:00",
    "Color": "#2D6A4F",
    "RichText": "<p>Test content</p>",
    "Code": "# test code",
    "Rating": 4,
    "Percent": 75.0,
    "Duration": 3600.0,
    "JSON": {},
}


def fake_value(fieldtype: str, fieldname: str, options: str | None = None) -> object:
    """Return a realistic fake value for the given fieldtype."""
    if fieldtype == "Select" and options:
        first = options.split("\n")[0].strip()
        return first if first else "Option1"
    val = _FAKE_VALUES.get(fieldtype, f"test_{fieldname}")
    if isinstance(val, str) and val == "Test Value":
        return f"Test {fieldname.replace('_', ' ').title()}"
    return val


def build_test_context(dt: dict) -> dict[str, Any]:
    """Prepare the template context for doctype/test.py.jinja."""
    name = dt["name"]
    snake = to_snake_case(name)
    fields = dt.get("fields", [])

    skip_types = {
        "Section",
        "Column",
        "Tab",
        "Table",
        "Empty",
        "Attach",
        "Image",
        "MultiLink",
        "Link",
        "Geolocation",
        "Signature",
        "BarCode",
        "HTMLEditor",
    }
    skip_names = {
        "name",
        "id",
        "docstatus",
        "idx",
        "owner",
        "creation",
        "modified",
        "modified_at",
        "modified_by",
        "created_at",
        "created_by",
    }

    required = [
        f
        for f in fields
        if f.get("required")
        and f["fieldtype"] not in skip_types
        and f["fieldname"] not in skip_names
    ]
    optional = [
        f
        for f in fields
        if not f.get("required")
        and f["fieldtype"] not in skip_types
        and f["fieldname"] not in skip_names
    ][:3]

    def _dict_repr(flist: list) -> str:
        if not flist:
            return "{}"
        items = [
            f'    "{f["fieldname"]}": {
                fake_value(f["fieldtype"], f["fieldname"], f.get("options"))!r
            }'
            for f in flist
        ]
        return "{\n" + ",\n".join(items) + ",\n}"

    assertions = [
        f'assert data["{f["fieldname"]}"] == {
            fake_value(f["fieldtype"], f["fieldname"], f.get("options"))!r
        }'
        for f in required
    ]

    update_flist = optional if optional else required[:1]

    return {
        "name": name,
        "snake": snake,
        "valid_payload": _dict_repr(required),
        "update_payload": _dict_repr(update_flist),
        "required_assertions": assertions,
        "missing_required_comment": (
            "# No required fields — empty payload may succeed"
            if not required
            else "# Required fields omitted intentionally"
        ),
        "missing_required_expected": (
            "assert resp.status_code in (200, 201, 422)"
            if not required
            else "assert resp.status_code == 422"
        ),
    }
