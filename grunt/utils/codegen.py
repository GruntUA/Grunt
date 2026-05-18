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

from grunt.document.base import SYS_FIELDS
from grunt.metadata.field import get_python_type
from grunt.utils.strings import to_snake_case

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BEGIN_MARKER = "# begin: auto-generated types"
_END_MARKER = "# end: auto-generated types"

_NON_PHYSICAL = {"Section", "Column", "Tab", "Empty"}


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
        if f.get("fieldtype") not in _NON_PHYSICAL and f.get("fieldname") not in SYS_FIELDS
    ]

    needs_datetime = any("datetime" in get_python_type(f["fieldtype"]) for f in physical)

    enriched = []
    for f in physical:
        enriched.append(
            {
                **f,
                "py_type": get_python_type(f["fieldtype"]),
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


def _render_type_block(fields: list[dict], indent: str = "    ") -> str:
    """Render only the auto-generated types block for insertion inside class body."""
    physical = [
        f
        for f in fields
        if f.get("fieldtype") not in _NON_PHYSICAL
        and f.get("fieldtype") != "Table"
        and f.get("fieldname") not in SYS_FIELDS
    ]
    table_fields = [
        f
        for f in fields
        if f.get("fieldtype") == "Table" and f.get("fieldname") not in SYS_FIELDS
    ]

    field_lines: list[str] = []
    for f in physical:
        py_type = get_python_type(f["fieldtype"])
        comment = f"  # {f['label']}" if f.get("label") and f["label"] != f["fieldname"] else ""
        field_lines.append(f"{indent}{f['fieldname']}: {py_type}{comment}")
    for f in table_fields:
        table_opt = f.get("options", "?")
        field_lines.append(f"{indent}{f['fieldname']}: list[dict]  # Table: {table_opt}")

    body = "\n".join(field_lines) if field_lines else f"{indent}name: str | None"

    return (
        f"{indent}{_BEGIN_MARKER}\n"
        f"{indent}# This code is auto-generated. Do not modify anything in this block.\n"
        f"\n"
        f"{body}\n"
        f"\n"
        f"{indent}{_END_MARKER}"
    )


def sync_controller_types(py_path: Path, name: str, fields: list[dict]) -> bool:
    """Update only the auto-generated types block inside an existing controller file.

    Replaces the region between *_BEGIN_MARKER* and *_END_MARKER*.
    If the markers are absent the block is inserted after the last top-level import.
    Custom code outside the markers is **never** touched.

    Returns True if the file was modified, False if already up-to-date.
    """
    source = py_path.read_text(encoding="utf-8")
    new_block = _render_type_block(fields, indent="    ")

    def _find_class_insert_offset(text: str) -> int | None:
        lines = text.splitlines(keepends=True)
        exact = (f"class {name}(", f"class {name}:")

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(exact):
                return sum(len(part) for part in lines[: i + 1])

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("class "):
                return sum(len(part) for part in lines[: i + 1])

        return None

    def _insert_block_into_class(text: str, block: str) -> str:
        insert_at = _find_class_insert_offset(text)
        if insert_at is None:
            suffix = "\n" if text.endswith("\n") else "\n\n"
            return text + suffix + block + "\n"

        rest = text[insert_at:]
        if rest.startswith("\n"):
            rest = rest[1:]
        return text[:insert_at] + "\n" + block + "\n\n" + rest

    begin_idx = source.find(_BEGIN_MARKER)
    end_idx = source.find(_END_MARKER)

    if begin_idx != -1 and end_idx != -1:
        block_line_start = source.rfind("\n", 0, begin_idx) + 1
        marker_indent = source[block_line_start:begin_idx]
        block_is_class_scoped = marker_indent == "    "

        end_of_block = end_idx + len(_END_MARKER)
        if block_is_class_scoped:
            # Replace class-scoped block in place.
            new_source = source[:begin_idx] + new_block + source[end_of_block:]
        else:
            # Legacy format had top-level block that declared a second class.
            # Remove it and reinsert as class-scoped annotations.
            while end_of_block < len(source) and source[end_of_block] in "\r\n":
                end_of_block += 1
            source_without_legacy_block = source[:begin_idx] + source[end_of_block:]
            new_source = _insert_block_into_class(source_without_legacy_block, new_block)
    else:
        new_source = _insert_block_into_class(source, new_block)

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
