"""``grunt doctype sync-types`` finds DocTypes inside the app's modules."""

import json
from types import SimpleNamespace

from click.testing import CliRunner

from grunt.cli import doctype as doctype_cli

CONTROLLER = '''from grunt.document.base import Document


class Thing(Document):
    # begin: auto-generated types
    # end: auto-generated types
    pass
'''


def _bench(tmp_path):
    dt_dir = tmp_path / "apps" / "shop" / "shop" / "doctypes" / "Thing"
    dt_dir.mkdir(parents=True)
    fields = [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}]
    (dt_dir / "Thing.json").write_text(json.dumps({"name": "Thing", "fields": fields}))
    (dt_dir / "Thing.py").write_text(CONTROLLER)
    return dt_dir / "Thing.py"


def test_sync_types_by_name_in_module(tmp_path, monkeypatch):
    py = _bench(tmp_path)
    monkeypatch.setattr(doctype_cli, "site_manager", SimpleNamespace(bench_dir=tmp_path))

    result = CliRunner().invoke(doctype_cli.doctype_sync_types, ["Thing", "--app", "shop"])

    assert result.exit_code == 0, result.output
    assert "title: str | None" in py.read_text()


def test_sync_types_all_needs_no_name(tmp_path, monkeypatch):
    py = _bench(tmp_path)
    monkeypatch.setattr(doctype_cli, "site_manager", SimpleNamespace(bench_dir=tmp_path))

    result = CliRunner().invoke(doctype_cli.doctype_sync_types, ["--all", "--app", "shop"])

    assert result.exit_code == 0, result.output
    assert "title: str | None" in py.read_text()


def test_required_fields_are_not_optional(tmp_path, monkeypatch):
    dt_dir = tmp_path / "apps" / "shop" / "shop" / "doctypes" / "Order"
    dt_dir.mkdir(parents=True)
    fields = [
        {"fieldname": "code", "label": "Code", "fieldtype": "Data", "required": True},
        {"fieldname": "note", "label": "Note", "fieldtype": "Data"},
    ]
    (dt_dir / "Order.json").write_text(json.dumps({"name": "Order", "fields": fields}))
    # framework-style snake_case controller file
    (dt_dir / "order.py").write_text(CONTROLLER.replace("Thing", "Order"))
    monkeypatch.setattr(doctype_cli, "site_manager", SimpleNamespace(bench_dir=tmp_path))

    result = CliRunner().invoke(doctype_cli.doctype_sync_types, ["Order", "--app", "shop"])

    assert result.exit_code == 0, result.output
    text = (dt_dir / "order.py").read_text()
    assert "code: str  # Code" in text
    assert "note: str | None  # Note" in text
