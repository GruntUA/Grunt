"""Permission rows in the ``actions`` format - core JSON and migration 0021."""

import json
from importlib import import_module
from pathlib import Path

import grunt

_CORE = Path(grunt.__file__).parent
_MIG = import_module("grunt.db.migrations.versions.0021_permission_actions")


def _core_rows():
    for path in sorted(_CORE.rglob("*.json")):
        if "node_modules" in path.parts:
            continue
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        if isinstance(data, dict) and "fields" in data:
            for row in data.get("permissions") or []:
                yield path.relative_to(_CORE), row


def test_core_rows_use_actions_and_grant_something():
    """A row granting nothing is a conversion slip (flags spelt 1/0 were once
    dropped this way) - every core row lists its actions."""
    bad = [
        str(path)
        for path, row in _core_rows()
        if not row.get("actions") or {"read", "write", "create", "delete"} & row.keys()
    ]
    assert bad == []


def test_migration_round_trip():
    data = {
        "permissions": [{"role": "A", "read": True, "write": 1, "create": False}],
        "permissions_base": [{"role": "A", "read": True}],
    }
    assert _MIG._clean("Thing", data)
    assert data["permissions"] == [{"role": "A", "actions": ["read", "write"]}]
    assert data["permissions_base"] == [{"role": "A", "actions": ["read"]}]
    assert not _MIG._clean("Thing", data)  # idempotent

    data["permissions"][0]["actions"].append("print")
    for row in data["permissions"] + data["permissions_base"]:
        assert _MIG._restore(row)
    assert data["permissions"] == [{"role": "A", "read": True, "write": True}]
    assert data["permissions_base"] == [{"role": "A", "read": True}]
