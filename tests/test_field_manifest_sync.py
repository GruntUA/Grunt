"""Guards against storage_class drifting between FieldType.column_spec and manifest.json.

See grunt.cli.fields.sync_manifests — run `grunt fields sync-manifests` to fix drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from grunt.metadata.field import get_registered_fieldtypes, get_storage_class

_FIELDS_DIR = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "fields"


def test_manifest_storage_class_matches_column_spec():
    drifted = []
    for fieldtype in get_registered_fieldtypes():
        manifest_path = _FIELDS_DIR / fieldtype / "manifest.json"
        if not manifest_path.exists():
            continue

        expected = get_storage_class(fieldtype)
        actual = json.loads(manifest_path.read_text(encoding="utf-8")).get("storage_class")
        if actual != expected:
            drifted.append(f"{fieldtype}: manifest={actual!r} column_spec={expected!r}")

    assert not drifted, (
        "manifest.json storage_class out of sync with column_spec "
        "(run `grunt fields sync-manifests`):\n" + "\n".join(drifted)
    )
