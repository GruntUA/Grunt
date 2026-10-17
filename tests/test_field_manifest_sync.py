"""Guards against manifest.json drifting from the backend FieldType definitions.

storage_class mirrors FieldType.column_spec, traits mirror FieldType.traits.
See grunt.cli.fields.sync_manifests — run `grunt fields sync-manifests` to fix drift.
"""

import json
from pathlib import Path

from grunt.metadata.field import get_manifest_attrs, get_registered_fieldtypes

_FIELDS_DIR = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "fields"


def test_manifest_matches_field_type():
    drifted = []
    for fieldtype in get_registered_fieldtypes():
        manifest_path = _FIELDS_DIR / fieldtype / "manifest.json"
        if not manifest_path.exists():
            continue

        expected = get_manifest_attrs(fieldtype)
        manifest = json.loads(manifest_path.read_text())
        actual = {key: manifest[key] for key in ("storage_class", "traits") if key in manifest}
        if actual != expected:
            drifted.append(f"{fieldtype}: manifest={actual!r} backend={expected!r}")

    assert not drifted, (
        "manifest.json out of sync with the backend FieldType "
        "(run `grunt fields sync-manifests`):\n" + "\n".join(drifted)
    )
