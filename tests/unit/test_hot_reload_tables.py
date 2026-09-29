"""Hot reload (`.reload_meta`) must drop compiled Tables too — a Table built
before a migration kept its old columns: a dropped column failed every SELECT
(«no such column: grunt_storage_file.path»), a new one was never read."""

from __future__ import annotations

import pytest

from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.doctype import DocType
from grunt.site import middleware
from grunt.site.manager import site_manager


def _dt(*fieldnames: str) -> DocType:
    return DocType.model_validate(
        {
            "name": "HotReloadProbe",
            "label": "Hot reload probe",
            "module": "core",
            "fields": [{"fieldname": f, "label": f, "fieldtype": "Data"} for f in fieldnames],
        }
    )


@pytest.mark.asyncio
async def test_reload_meta_recompiles_tables(tmp_path, monkeypatch):
    site = "__pytest__"
    monkeypatch.setattr(site_manager, "sites_dir", tmp_path)
    (tmp_path / site).mkdir()

    before = compile_doctype_to_table(_dt("kept", "dropped"))
    assert "dropped" in before.c
    # Same DocType name, new definition: without a reload the old Table is reused.
    assert "dropped" in compile_doctype_to_table(_dt("kept", "added")).c

    (tmp_path / site / ".reload_meta").touch()
    await middleware._apply_hot_reload_if_triggered(site)

    after = compile_doctype_to_table(_dt("kept", "added"))
    assert "dropped" not in after.c
    assert "added" in after.c
    assert not (tmp_path / site / ".reload_meta").exists()
