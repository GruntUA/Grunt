"""Tests for grunt.scripting.file_scripts — file-based server script discovery.

Regression: _load_doctype_dir_scripts skipped "the controller file" by
comparing py_file.stem (snake_case, e.g. "doc_type") to the DocType
directory name (PascalCase, e.g. "DocType") — always False, since real
controller files are snake_case in practice (see
DocumentRegistry.index_core_controllers, the actual controller loader).
Every controller .py file in the framework was therefore being swept up
and registered as a bogus "API (auto)" server script under its snake_case
filename.
"""

from __future__ import annotations

from grunt.scripting import file_scripts
from grunt.scripting.file_scripts import (
    FILE_SCRIPT_REGISTRY,
    _load_doctype_dir_scripts,
    discover_file_scripts,
    get_file_client_scripts,
)


def _make_doctype_dir(tmp_path, doctype_name: str, controller_filename: str, extra_files=None):
    dt_dir = tmp_path / "doctypes" / doctype_name
    dt_dir.mkdir(parents=True)
    (dt_dir / f"{controller_filename}.py").write_text(f"class {doctype_name}:\n    pass\n")
    for name, content in (extra_files or {}).items():
        (dt_dir / f"{name}.py").write_text(content)
    return dt_dir


class TestControllerFileNotRegisteredAsScript:
    def setup_method(self):
        self._saved = dict(FILE_SCRIPT_REGISTRY)
        FILE_SCRIPT_REGISTRY.clear()

    def teardown_method(self):
        FILE_SCRIPT_REGISTRY.clear()
        FILE_SCRIPT_REGISTRY.update(self._saved)

    def test_snake_case_controller_skipped(self, tmp_path):
        """The real-world case: DocType dir "DocType", controller "doc_type.py"."""
        dt_dir = _make_doctype_dir(tmp_path, "DocType", "doc_type")
        _load_doctype_dir_scripts(dt_dir, "grunt")
        assert ("api", "doc_type") not in FILE_SCRIPT_REGISTRY

    def test_pascal_case_controller_skipped(self, tmp_path):
        """Legacy convention: controller named exactly like the DocType dir."""
        dt_dir = _make_doctype_dir(tmp_path, "Applicant", "Applicant")
        _load_doctype_dir_scripts(dt_dir, "grunt")
        assert ("api", "Applicant") not in FILE_SCRIPT_REGISTRY

    def test_extra_script_still_registered(self, tmp_path):
        """A genuine extra server script alongside the controller is unaffected."""
        dt_dir = _make_doctype_dir(
            tmp_path,
            "Applicant",
            "applicant",
            extra_files={
                "validate_tax_id": (
                    "# Script Type: API\n# Method: validate_tax_id\nresult = True\n"
                )
            },
        )
        _load_doctype_dir_scripts(dt_dir, "grunt")
        assert ("api", "doc_type") not in FILE_SCRIPT_REGISTRY  # unrelated sanity check
        assert ("api", "validate_tax_id") in FILE_SCRIPT_REGISTRY
        assert ("api", "applicant") not in FILE_SCRIPT_REGISTRY


def test_discover_file_scripts_finds_nested_package_doctypes(tmp_path):
    """Nested framework layouts like grunt/metadata/doctypes/{Name}/{Name}.js must scan."""
    app_dir = tmp_path / "bench" / "apps" / "grunt"
    dt_dir = app_dir / "metadata" / "doctypes" / "DocType"
    dt_dir.mkdir(parents=True)
    (dt_dir / "DocType.js").write_text(
        "function on_load(frm) { frm.add_menu_item('Test', () => {}); }\n"
    )

    discover_file_scripts(app_dir.parent)
    scripts = get_file_client_scripts("DocType")

    assert scripts
    assert any(s["name"].endswith(":DocType.js") for s in scripts)


def test_framework_global_form_script_loads_before_doctype_script(tmp_path, monkeypatch):
    doctypes_dir = tmp_path / "metadata" / "doctypes"
    global_dir = doctypes_dir / "DocType"
    global_dir.mkdir(parents=True)
    (global_dir / "global_form.js").write_text("function on_load(frm) {}\n")
    (global_dir / "global_list.js").write_text("function setup_list(listview) {}\n")

    page_dir = doctypes_dir / "Page"
    page_dir.mkdir()
    (page_dir / "Page.js").write_text("function on_load(frm) {}\n")

    monkeypatch.setattr(file_scripts, "_client_script_dirs", [("grunt", doctypes_dir)])
    monkeypatch.setattr(file_scripts, "FILE_CLIENT_SCRIPT_REGISTRY", {})
    monkeypatch.setattr(file_scripts, "_client_script_scanned", set())

    scripts = get_file_client_scripts("Page")

    assert [script["name"] for script in scripts] == [
        "grunt:global_form.js",
        "grunt:global_list.js",
        "grunt:Page.js",
    ]
