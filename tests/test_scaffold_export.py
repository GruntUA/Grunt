"""export_doctype_files: a same-named DocType of another module is never overwritten."""

import json

from grunt.metadata.doctype import DocType
from grunt.metadata.scaffold import export_doctype_files
from grunt.site.manager import site_manager


def test_other_modules_json_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(site_manager, "bench_dir", tmp_path)
    own = tmp_path / "apps" / "shop" / "shop" / "doctypes" / "Contract" / "Contract.json"
    own.parent.mkdir(parents=True)
    original = {"name": "Contract", "module": "shop", "fields": []}
    own.write_text(json.dumps(original))

    # a test/Studio DocType of another module with the same name and no owning app
    assert (
        export_doctype_files(DocType(name="Contract", label="Contract", module="core", fields=[]))
        is None
    )
    assert json.loads(own.read_text()) == original

    # the owning module still updates its own file in place
    path = export_doctype_files(DocType(name="Contract", label="Договір", module="shop", fields=[]))
    assert path == str(own)
    assert json.loads(own.read_text())["label"] == "Договір"
