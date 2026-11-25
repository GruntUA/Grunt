"""Code generation utilities for Grunt.

Provides:
  - Template rendering via Jinja2 (with app-level override support)
  - Smart controller type-block sync (replaces only auto-generated section)
  - Fieldtype -> Python type mapping helpers
"""

import ast
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from grunt.document.base import SYS_FIELDS, is_shadowed_field
from grunt.metadata.field import get_python_type, is_physical_fieldtype
from grunt.utils import import_graph
from grunt.utils.strings import to_snake_case

# Constants

_BEGIN_MARKER = "# begin: auto-generated types"
_END_MARKER = "# end: auto-generated types"

_DATETIME_NAMES = ("date", "datetime", "time")


# Template environment


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


# Field helpers


def _is_typed(f: dict) -> bool:
    """A field that holds a value of its own (a column or a child table)."""
    fieldtype = f.get("fieldtype") or ""
    return f.get("fieldname") not in SYS_FIELDS and (
        is_physical_fieldtype(fieldtype) or fieldtype == "Table"
    )


def is_required_on_create(f: dict) -> bool:
    """A field the constructor must be given: required, and nothing else fills it."""
    return bool(
        f.get("required")
        and f.get("default") in (None, "")
        and not f.get("fetch_from")
        and not f.get("read_only")
        and f.get("fieldtype") != "Check"
    )


def field_type(f: dict) -> str:
    """Python type of a field; one the constructor must be given is never None."""
    py_type = get_python_type(f["fieldtype"])
    if is_required_on_create(f) and py_type.endswith(" | None"):
        py_type = py_type.removesuffix(" | None")
    return py_type


def _from_import(module: str, names: list[str]) -> str:
    """``from <module> import <names>`` - wrapped as ruff format does past 100 columns."""
    line = f"from {module} import {', '.join(names)}"
    if len(line) <= 100:
        return line
    body = "".join(f"    {n},\n" for n in names)
    return f"from {module} import (\n{body})"


def _import_key(name: str) -> tuple[int, str]:
    """isort/ruff order-by-type: CONSTANTS, then Classes, then the rest."""
    kind = 0 if name.isupper() and len(name) > 1 else 1 if name[0].isupper() else 2
    return kind, name.lower()


def build_controller_context(
    name: str, fields: list[dict], py_path: Path | None = None
) -> dict[str, Any]:
    """Prepare the template context for doctype/controller.py.jinja.

    *py_path* - where the controller is written: a child table is typed with
    its controller's class when one is found from there (``list[OrderItem]``).
    """
    children = child_classes(fields, py_path)
    imports = block_imports(fields, children=children)
    stdlib = {m: n for m, n in imports.items() if _is_stdlib(m)}
    first_party = {m: n for m, n in imports.items() if not _is_stdlib(m)}
    first_party.setdefault("grunt.document.base", []).append("Document")
    return {
        "name": name,
        "imports": [_from_import(m, n) for m, n in sorted(stdlib.items())],
        "first_party_imports": [
            _from_import(m, sorted(n, key=_import_key)) for m, n in sorted(first_party.items())
        ],
        "type_block": _render_type_block(fields, children=children),
    }


# Child tables: list[ChildCls]

_CORE_PACKAGE = Path(__file__).resolve().parent.parent  # grunt/


@dataclass(frozen=True)
class ChildClass:
    """The controller class a child table's rows are typed with."""

    module: str
    name: str
    #: Imported under ``if TYPE_CHECKING:`` - a plain import would close an import cycle.
    type_checking: bool = False


def _is_stdlib(module: str) -> bool:
    return module.split(".")[0] in sys.stdlib_module_names


def _package_top(path: Path) -> Path | None:
    """The top package directory *path* is in (``grunt/``, ``apps/hrm/hrm/``) -
    the folder under the project's ``pyproject.toml`` (a DocType folder may be a
    namespace package, without ``__init__.py``)."""
    path = path.resolve()
    for d in path.parents:
        if (d / "pyproject.toml").exists():
            top = d / path.relative_to(d).parts[0]
            return top if (top / "__init__.py").exists() else None
    return None


def _module_name(path: Path, top: Path) -> str:
    parts = list(path.resolve().relative_to(top.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _find_controller(doctype: str, tops: list[Path]) -> Path | None:
    """The controller file of *doctype* (``…/doctypes/<DocType>/*.py`` defining
    ``class <DocType>``) in the first of *tops* that has one."""
    for top in tops:
        for folder in sorted(top.glob(f"**/doctypes/{doctype}")):
            for py in sorted(folder.glob("*.py")):
                if py.name == "__init__.py":
                    continue
                try:
                    tree = ast.parse(py.read_text(encoding="utf-8"))
                except OSError, SyntaxError:
                    continue
                if any(isinstance(n, ast.ClassDef) and n.name == doctype for n in tree.body):
                    return py
    return None


_graphs: dict[Path, tuple[float, import_graph.ImportGraph]] = {}


def _graph(top: Path) -> import_graph.ImportGraph:
    """The import graph of the package *top* - rebuilt once a file of it changes."""
    newest = max((p.stat().st_mtime for p in top.rglob("*.py")), default=0.0)
    cached = _graphs.get(top)
    if cached is None or cached[0] != newest:
        cached = (newest, import_graph.build(top.parent, top.name, skip=("/tests/",)))
        _graphs[top] = cached
    return cached[1]


def _imports_reach(top: Path, start: str, target: str) -> bool:
    """Whether *start* already imports *target*, directly or through other modules."""
    edges = _graph(top).edges
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in edges.get(queue.popleft(), {}):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def child_classes(fields: list[dict], py_path: Path | None) -> dict[str, ChildClass]:
    """``fieldname -> ChildClass`` for the child tables of the controller at
    *py_path* whose child DocType has a controller - looked up in the
    controller's own package, then in the core. Imported plainly unless the
    child already imports the parent (an import cycle): then under TYPE_CHECKING."""
    tables = [
        f for f in fields if _is_typed(f) and f.get("fieldtype") == "Table" and f.get("options")
    ]
    if not tables or py_path is None:
        return {}
    top = _package_top(py_path)
    if top is None:
        return {}
    parent = _module_name(py_path, top)
    found: dict[str, ChildClass] = {}
    for f in tables:
        doctype = f["options"]
        child_py = _find_controller(doctype, list(dict.fromkeys([top, _CORE_PACKAGE])))
        if child_py is None or child_py.resolve() == py_path.resolve():
            continue
        child_top = _package_top(child_py)
        if child_top is None:
            continue
        module = _module_name(child_py, child_top)
        try:
            cycle = child_top == top and _imports_reach(top, module, parent)
        except SyntaxError:  # a file of the package doesn't parse: no import at run time
            cycle = True
        found[f["fieldname"]] = ChildClass(module, doctype, type_checking=cycle)
    return found


# Smart controller sync


def _render_type_block(
    fields: list[dict], indent: str = "    ", children: dict[str, ChildClass] | None = None
) -> str:
    """Render only the auto-generated types block for insertion inside class body."""
    children = children or {}
    physical = [f for f in fields if _is_typed(f) and f.get("fieldtype") != "Table"]
    table_fields = [f for f in fields if _is_typed(f) and f.get("fieldtype") == "Table"]

    field_lines: list[str] = []
    for f in physical + table_fields:
        if is_shadowed_field(f["fieldname"]):
            name = f["fieldname"]
            field_lines.append(
                f'{indent}# "{name}" field: read it as self.data["{name}"] - '
                f"self.{name} is taken by the controller."
            )
    physical = [f for f in physical if not is_shadowed_field(f["fieldname"])]
    table_fields = [f for f in table_fields if not is_shadowed_field(f["fieldname"])]
    # Annotations type the constructor too (Document is a dataclass_transform):
    # `= None` / `= []` - a field it may be called without.
    for f in physical:
        py_type = field_type(f)
        default = " = None" if py_type.endswith(" | None") else ""
        comment = f"  # {f['label']}" if f.get("label") and f["label"] != f["fieldname"] else ""
        field_lines.append(f"{indent}{f['fieldname']}: {py_type}{default}{comment}")
    for f in table_fields:
        default = "" if is_required_on_create(f) else " = []"
        child = children.get(f["fieldname"])
        if child is not None:
            comment = f"  # {f['label']}" if f.get("label") and f["label"] != f["fieldname"] else ""
            field_lines.append(f"{indent}{f['fieldname']}: list[{child.name}]{default}{comment}")
        else:
            table_opt = f.get("options", "?")
            field_lines.append(
                f"{indent}{f['fieldname']}: list[dict]{default}  # Table: {table_opt}"
            )

    body = "\n".join(field_lines) if field_lines else f"{indent}pass"

    return (
        f"{indent}{_BEGIN_MARKER}\n"
        f"{indent}# This code is auto-generated. Do not modify anything in this block.\n"
        f"\n"
        f"{body}\n"
        f"\n"
        f"{indent}{_END_MARKER}"
    )


def block_imports(
    fields: list[dict], *, children: dict[str, ChildClass] | None = None
) -> dict[str, list[str]]:
    """``module -> names`` the types block of *fields* needs imported (a child
    controller imported under TYPE_CHECKING is left out)."""
    used = {
        name
        for f in fields
        if _is_typed(f) and f.get("fieldtype") != "Table"
        for name in re.findall(r"[A-Za-z_]\w*", field_type(f))
    }
    imports = {"datetime": [n for n in _DATETIME_NAMES if n in used]}
    if "Any" in used:
        imports["typing"] = ["Any"]
    for child in (children or {}).values():
        if not child.type_checking:
            imports.setdefault(child.module, []).append(child.name)
    return {module: names for module, names in imports.items() if names}


def _ensure_block_imports(
    source: str, fields: list[dict], children: dict[str, ChildClass] | None = None
) -> str:
    """Make sure the module imports the names the types block annotates with."""
    for module, needed in block_imports(fields, children=children).items():
        source = _ensure_import(source, module, needed)
    for child in (children or {}).values():
        if child.type_checking:
            source = _ensure_type_checking_import(source, child.module, child.name)
    return source


def _ensure_type_checking_import(source: str, module: str, name: str) -> str:
    """``from <module> import <name>`` under ``if TYPE_CHECKING:``, unless the
    module imports it already."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    if any(
        isinstance(n, ast.ImportFrom)
        and n.module == module
        and any(a.name == name for a in n.names)
        for n in ast.walk(tree)
    ):
        return source
    source = _ensure_import(source, "typing", ["TYPE_CHECKING"])
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    imports = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    end = max((n.end_lineno or n.lineno) for n in imports) if imports else 0
    stmt = _from_import(module, [name]).replace("\n", "\n    ")
    lines.insert(end, f"\nif TYPE_CHECKING:\n    {stmt}\n")
    return "".join(lines)


def _ensure_import(source: str, module: str, needed: list[str]) -> str:
    """Make sure `from <module> import ...` covers *needed*."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines(keepends=True)

    imports = [
        n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == module and not n.level
    ]
    # Only an unaliased import binds the bare name the block annotates with.
    bound = {a.name for n in imports for a in n.names if a.asname in (None, a.name)}
    missing = [n for n in needed if n not in bound]
    if not missing:
        return source

    stmt = _from_import(module, missing) + "\n"
    for node in imports:
        if node.end_lineno == node.lineno and not any(a.asname for a in node.names):
            merged = sorted({*(a.name for a in node.names), *missing}, key=_import_key)
            lines[node.lineno - 1] = _from_import(module, merged) + "\n"
            return "".join(lines)
    if imports:
        # Multi-line or aliased: leave it as it is, add the names on a line of their own.
        end = imports[-1].end_lineno or imports[-1].lineno
        lines.insert(end, stmt)
        return "".join(lines)

    if not _is_stdlib(module):
        # In order among the module-level `from` imports of the same package.
        package = module.split(".")[0]
        section = [
            n
            for n in tree.body
            if isinstance(n, ast.ImportFrom)
            and not n.level
            and not getattr(n, "is_lazy", False)
            and (n.module or "").split(".")[0] == package
        ]
        later = next((n for n in section if (n.module or "") > module), None)
        if later is not None:
            lines.insert(later.lineno - 1, stmt)
            return "".join(lines)
        if section:
            lines.insert(section[-1].end_lineno or section[-1].lineno, stmt)
            return "".join(lines)

    for node in tree.body:
        if (
            isinstance(node, ast.Import | ast.ImportFrom)
            and getattr(node, "module", None) != "__future__"
        ):
            top = (node.names[0].name if isinstance(node, ast.Import) else node.module or "").split(
                "."
            )[0]
            sep = "" if top in sys.stdlib_module_names else "\n"
            lines.insert(node.lineno - 1, stmt + sep)
            return "".join(lines)
    return source


def sync_controller_types(py_path: Path, name: str, fields: list[dict]) -> bool:
    """Update only the auto-generated types block inside an existing controller file.

    Replaces the region between *_BEGIN_MARKER* and *_END_MARKER*.
    If the markers are absent the block is inserted after the last top-level import.
    Custom code outside the markers is **never** touched.

    Returns True if the file was modified, False if already up-to-date.
    """
    source = py_path.read_text()
    children = child_classes(fields, py_path)
    new_block = _render_type_block(fields, indent="    ", children=children)

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
        return text[:insert_at] + block + "\n\n" + rest

    begin_idx = source.find(_BEGIN_MARKER)
    end_idx = source.find(_END_MARKER)

    if begin_idx != -1 and end_idx != -1:
        block_line_start = source.rfind("\n", 0, begin_idx) + 1
        marker_indent = source[block_line_start:begin_idx]
        # Class-scoped when the marker line is whitespace-indented (the normal
        # case). Any spaces count - not just exactly four - so a file whose
        # indentation has already crept stays recognised and gets normalised.
        block_is_class_scoped = marker_indent != "" and marker_indent.strip() == ""

        end_of_block = end_idx + len(_END_MARKER)
        if block_is_class_scoped:
            # Replace class-scoped block in place. Slice from the START of the
            # marker line, not from `begin_idx`: `new_block` carries its own
            # indentation, so keeping the old indent here would duplicate it and
            # creep every method below the block one level deeper per sync.
            new_source = source[:block_line_start] + new_block + source[end_of_block:]
        else:
            # Legacy format had top-level block that declared a second class.
            # Remove it and reinsert as class-scoped annotations.
            while end_of_block < len(source) and source[end_of_block] in "\r\n":
                end_of_block += 1
            source_without_legacy_block = source[:block_line_start] + source[end_of_block:]
            new_source = _insert_block_into_class(source_without_legacy_block, new_block)
    else:
        new_source = _insert_block_into_class(source, new_block)

    new_source = _ensure_block_imports(new_source, fields, children)

    if new_source == source:
        return False

    py_path.write_text(new_source)
    return True


# Test generation helpers

_FAKE_VALUES: dict[str, object] = {
    "Data": "Test Value",
    "LongText": "Long text content",
    "Int": 42,
    "Float": 3.14,
    "Currency": 1250.5,
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
        "Attach",
        "Image",
        "MultiLink",
        "Link",
        "Geolocation",
        "Signature",
        "BarCode",
        "HTMLView",
    }
    skip_names = {
        "name",
        "id",
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
